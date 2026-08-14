import os
import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from dotenv import load_dotenv
import yfinance as yf
import google.generativeai as genai  # ✅ Correct import

# Import MongoDB module
from mongodb import (
    init_db, get_tier, set_tier, get_watchlist, add_ticker, 
    remove_ticker, get_watchlist_count, can_add_stock, is_pro_user,
    FREE_TIER_LIMIT, check_connection
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# ============================================================
# ✅ Configure GenAI (Gemini) - using google.generativeai
# ============================================================
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set - AI features will be disabled")
        gemini_model = None
    else:
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        logger.info("Gemini AI initialized successfully")
except Exception as e:
    logger.error(f"Gemini initialization error: {e}")
    gemini_model = None

# Initialize MongoDB on startup
try:
    init_db()
    logger.info("MongoDB initialized successfully")
except Exception as e:
    logger.error(f"MongoDB initialization error: {e}")


# ============================================================
# --- Decorators ---
# ============================================================
def require_pro(f):
    """Decorator to restrict endpoints to Pro users."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        tier = get_tier()
        if tier != "pro":
            return jsonify({
                "error": "Pro feature required",
                "message": "Upgrade to Pro to access this feature"
            }), 403
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# --- Helper Functions ---
# ============================================================
def fetch_ohlc(symbol, period="1mo", interval="1d"):
    """Pull OHLC candles from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return []

        hist = hist.reset_index()
        date_col = "Date" if "Date" in hist.columns else "Datetime"
        
        result = []
        for _, row in hist.iterrows():
            result.append({
                "date": row[date_col].isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"])
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching OHLC for {symbol}: {e}")
        return []


def get_stock_info(symbol):
    """Get current stock information."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Get current price
        hist = ticker.history(period="1d")
        current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
        
        return {
            "symbol": symbol.upper(),
            "price": current_price,
            "change": info.get("regularMarketChange", 0),
            "change_percent": info.get("regularMarketChangePercent", 0),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "eps": info.get("trailingEps", 0),
            "volume": info.get("volume", 0),
            "sector": info.get("sector", "Unknown")
        }
    except Exception as e:
        logger.error(f"Error fetching stock info for {symbol}: {e}")
        return None


# ============================================================
# --- Routes ---
# ============================================================

# Health check endpoint
@app.route('/api/health')
def health_check():
    """Health check endpoint for Render."""
    return jsonify({
        "status": "healthy",
        "gemini_available": gemini_model is not None,
        "mongodb_connected": check_connection() if check_connection else False,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@app.route('/')
def index():
    """Serve the main dashboard."""
    return render_template('index.html')


@app.route('/api/stock/<symbol>')
def get_stock(symbol):
    """Get stock data for a symbol."""
    data = get_stock_info(symbol)
    if data:
        return jsonify(data), 200
    return jsonify({"error": "Stock not found"}), 404


@app.route('/api/stock/<symbol>/ohlc')
def get_ohlc(symbol):
    """Get OHLC data for a symbol."""
    period = request.args.get('period', '1mo')
    interval = request.args.get('interval', '1d')
    data = fetch_ohlc(symbol, period, interval)
    return jsonify(data), 200


# ============================================================
# ✅ AI-Powered Stock Analysis Route
# ============================================================
@app.route('/api/analyze', methods=['POST'])
def analyze_stock():
    """AI-powered stock analysis using Gemini."""
    if gemini_model is None:
        return jsonify({
            "error": "Gemini AI is not available. Please check GEMINI_API_KEY."
        }), 503
    
    data = request.json
    symbol = data.get('symbol', 'AAPL')
    
    try:
        response = gemini_model.generate_content(
            f"Provide a brief investment analysis of {symbol} stock. "
            f"Include: Current sentiment (Bullish/Bearish/Neutral), "
            f"Key strengths, Key risks, Short-term outlook, Long-term outlook. "
            f"Keep response under 200 words."
        )
        return jsonify({
            "symbol": symbol,
            "analysis": response.text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Gemini analysis error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# --- Watchlist Routes ---
# ============================================================
@app.route('/api/watchlist')
def get_watchlist_endpoint():
    """Get user's watchlist."""
    watchlist = get_watchlist()
    return jsonify({
        "watchlist": watchlist,
        "count": len(watchlist),
        "limit": FREE_TIER_LIMIT,
        "is_pro": is_pro_user()
    }), 200


@app.route('/api/watchlist/add', methods=['POST'])
def add_watchlist_stock():
    """Add a stock to the watchlist."""
    data = request.json
    symbol = data.get('symbol', '').upper()
    
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
    
    # Check if user can add more stocks
    if not can_add_stock():
        return jsonify({
            "error": "Watchlist limit reached",
            "message": f"Free tier allows only {FREE_TIER_LIMIT} stocks. Upgrade to Pro for unlimited."
        }), 403
    
    result = add_ticker(symbol)
    if result:
        return jsonify({"message": f"{symbol} added to watchlist"}), 200
    return jsonify({"error": "Failed to add stock"}), 400


@app.route('/api/watchlist/remove/<symbol>', methods=['DELETE'])
def remove_watchlist_stock(symbol):
    """Remove a stock from the watchlist."""
    result = remove_ticker(symbol.upper())
    if result:
        return jsonify({"message": f"{symbol} removed from watchlist"}), 200
    return jsonify({"error": "Stock not found in watchlist"}), 404


# ============================================================
# --- User Tier Routes ---
# ============================================================
@app.route('/api/user/tier')
def get_user_tier():
    """Get user's current tier."""
    return jsonify({
        "tier": get_tier(),
        "watchlist_count": get_watchlist_count(),
        "max_allowed": FREE_TIER_LIMIT if get_tier() == "free" else "unlimited"
    }), 200


@app.route('/api/user/upgrade', methods=['POST'])
@require_pro
def upgrade_to_pro():
    """Upgrade user to Pro (simulated)."""
    result = set_tier("pro")
    if result:
        return jsonify({"message": "Successfully upgraded to Pro!", "tier": "pro"}), 200
    return jsonify({"error": "Failed to upgrade"}), 500


# ============================================================
# --- Error Handlers ---
# ============================================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


# ============================================================
# --- Main Entry Point ---
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
