import os
import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from dotenv import load_dotenv
import yfinance as yf
import google.generativeai as genai

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

# Configure GenAI (Gemini)
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set - AI features will be disabled")
        genai = None
        gemini_model = None
    else:
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")  # Updated to latest available
        logger.info("Gemini AI initialized successfully")
except Exception as e:
    logger.error(f"Gemini initialization error: {e}")
    genai = None
    gemini_model = None

# Initialize MongoDB on startup
try:
    init_db()
    logger.info("MongoDB initialized successfully")
except Exception as e:
    logger.error(f"MongoDB initialization error: {e}")


# --- Decorators ---
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


# --- Helper Functions ---
def fetch_ohlc(symbol, period="1mo", interval="1d"):
    """Pull OHLC candles from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return []

        hist = hist.reset_index()
        date_col = "Date" if "Date" in hist.columns else "Datetime"

        ohlc = []
        for _, row in hist.iterrows():
            date_val = row[date_col]
            ohlc.append({
                "date": date_val.strftime("%Y-%m-%d %H:%M") if hasattr(date_val, "strftime") else str(date_val),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            })
        return ohlc
    except Exception as e:
        logger.error(f"Error fetching OHLC for {symbol}: {e}")
        raise


def get_stock_analysis(symbol, ohlc_data):
    """Get AI analysis for a stock."""
    if not gemini_model:
        return "AI analysis unavailable. Please set GEMINI_API_KEY."

    try:
        recent = ohlc_data[-10:] if len(ohlc_data) > 10 else ohlc_data
        prices = [c["close"] for c in recent]
        price_change = ((prices[-1] - prices[0]) / prices[0] * 100) if prices else 0
        
        prompt = f"""
        You are a market analyst. Analyze this stock:

        Symbol: {symbol}
        Recent closing prices: {prices[-5:]}
        Price change (10 days): {price_change:.2f}%
        
        Give a brief analysis including:
        1. A BULLISH or BEARISH verdict
        2. 2-3 sentence rationale
        3. Key support/resistance levels if visible
        
        Keep it concise and accessible to retail investors.
        """
        
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"AI analysis error for {symbol}: {e}")
        return f"AI analysis temporarily unavailable: {str(e)}"


# --- Routes ---
@app.route('/', methods=['GET'])
def home():
    """Main dashboard page."""
    try:
        watchlist = get_watchlist()
        tier = get_tier()
        is_pro = tier == "pro"
        count = len(watchlist)
        can_add = is_pro or count < FREE_TIER_LIMIT
        
        return render_template(
            'index.html',
            watchlist=watchlist,
            tier=tier,
            is_pro=is_pro,
            count=count,
            limit=FREE_TIER_LIMIT,
            can_add=can_add,
            mongo_available=check_connection()
        )
    except Exception as e:
        logger.error(f"Error rendering home: {e}")
        return render_template('index.html', error="Database connection issue"), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint for Render."""
    mongo_status = check_connection()
    gemini_status = gemini_model is not None
    
    status = {
        "status": "healthy" if mongo_status else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "mongodb": "connected" if mongo_status else "disconnected",
            "gemini": "available" if gemini_status else "unavailable",
            "watchlist_count": get_watchlist_count(),
            "tier": get_tier()
        }
    }
    
    # Return 503 if MongoDB is down but service can still function with fallback
    if not mongo_status:
        return jsonify(status), 503
    return jsonify(status), 200


@app.route('/api/watchlist', methods=['GET'])
def get_watchlist_api():
    """Get current watchlist."""
    try:
        watchlist = get_watchlist()
        tier = get_tier()
        is_pro = tier == "pro"
        count = len(watchlist)
        
        return jsonify({
            "success": True,
            "watchlist": watchlist,
            "count": count,
            "tier": tier,
            "is_pro": is_pro,
            "limit": FREE_TIER_LIMIT if not is_pro else None,
            "can_add": is_pro or count < FREE_TIER_LIMIT
        })
    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/watchlist', methods=['POST'])
def add_watchlist():
    """Add a ticker to watchlist."""
    data = request.get_json()
    ticker = (data.get('ticker') or '').strip().upper()
    
    if not ticker:
        return jsonify({"success": False, "error": "No ticker provided"}), 400
    
    # Check if user can add more stocks
    if not can_add_stock():
        return jsonify({
            "success": False, 
            "error": f"Free tier limit of {FREE_TIER_LIMIT} stocks reached. Upgrade to Pro!"
        }), 403
    
    try:
        # Validate ticker exists
        ohlc = fetch_ohlc(ticker, period="1d", interval="1d")
        if not ohlc:
            return jsonify({"success": False, "error": f"Invalid ticker: {ticker}"}), 404
        
        add_ticker(ticker)
        return jsonify({"success": True, "message": f"Added {ticker} to watchlist"})
    except Exception as e:
        logger.error(f"Error adding ticker {ticker}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/watchlist/<ticker>', methods=['DELETE'])
def remove_watchlist(ticker):
    """Remove a ticker from watchlist."""
    try:
        remove_ticker(ticker.upper())
        return jsonify({"success": True, "message": f"Removed {ticker} from watchlist"})
    except Exception as e:
        logger.error(f"Error removing ticker {ticker}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/chart', methods=['GET'])
def chart():
    """Chart data for Plotly candlestick."""
    symbol = request.args.get('symbol', '').strip().upper()
    period = request.args.get('period', '1mo')
    interval = request.args.get('interval', '1d')

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    try:
        ohlc = fetch_ohlc(symbol, period, interval)
        if not ohlc:
            return jsonify({"error": f"No chart data found for {symbol}"}), 404
        return jsonify({
            "success": True,
            "symbol": symbol, 
            "period": period, 
            "interval": interval, 
            "ohlc": ohlc,
            "count": len(ohlc)
        })
    except Exception as e:
        logger.error(f"Chart error for {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Analyze a stock."""
    data = request.get_json()
    symbol = (data.get('symbol') or data.get('ticker') or '').strip().upper()
    
    if not symbol:
        return jsonify({"error": "No ticker provided"}), 400

    try:
        ohlc = fetch_ohlc(symbol, period="1mo", interval="1d")
        if not ohlc:
            return jsonify({"error": f"No price data found for {symbol}"}), 404

        # Get current price
        current_price = ohlc[-1]["close"] if ohlc else 0
        price_change = ((ohlc[-1]["close"] - ohlc[0]["close"]) / ohlc[0]["close"] * 100) if len(ohlc) > 1 else 0

        # Get AI analysis
        analysis = get_stock_analysis(symbol, ohlc)

        return jsonify({
            "success": True,
            "symbol": symbol,
            "current_price": current_price,
            "price_change": price_change,
            "data_points": len(ohlc),
            "analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error(f"Analysis error for {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/tier', methods=['GET'])
def get_tier_api():
    """Get current user tier."""
    try:
        tier = get_tier()
        return jsonify({
            "success": True,
            "tier": tier,
            "is_pro": tier == "pro",
            "free_limit": FREE_TIER_LIMIT,
            "watchlist_count": get_watchlist_count()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/tier', methods=['POST'])
def set_tier_api():
    """Set user tier (admin only in production)."""
    data = request.get_json()
    tier = data.get('tier', 'free')
    
    if tier not in ['free', 'pro']:
        return jsonify({"success": False, "error": "Invalid tier"}), 400
    
    try:
        set_tier(tier)
        return jsonify({"success": True, "tier": tier})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/pro', methods=['GET'])
def pro_page():
    """Pro upgrade page."""
    tier = get_tier()
    return render_template('pro.html', tier=tier, is_pro=tier == "pro")


@app.route('/api/upgrade', methods=['POST'])
def upgrade_to_pro():
    """Simulate upgrading to Pro (demo-gated)."""
    try:
        # In production, verify Stripe payment here
        set_tier("pro")
        return jsonify({"success": True, "message": "Upgraded to Pro!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


# --- Main ---
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(host='0.0.0.0', port=port, debug=debug)


# backend flask app
@app.route('/stream/<symbol>', methods=['GET'])
def stream_ticker(symbol):
    """Stream live price updates via Server-Sent Events"""
    
    @stream_with_context
    def generate():
        ticker = yf.Ticker(symbol)
        last_price = None
        
        try:
            while True:
                # Fetch current price
                data = ticker.history(period="1d", interval="1m")
                
                if not data.empty:
                    current_price = float(data['Close'].iloc[-1])
                    
                    # Only send update if price changed
                    if current_price != last_price:
                        last_price = current_price
                        yield f"data: {json.dumps({'price': current_price})}\n\n"
                
                # Wait 5 seconds before next update (avoid rate limits)
                time.sleep(5)
                
        except GeneratorExit:
            # Client disconnected
            pass
        except Exception as e:
            # Send error
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
            'Connection': 'keep-alive'
        }
    )
