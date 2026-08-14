import os
import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
import yfinance as yf
import google.generativeai as genai

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
# ✅ Configure GenAI (Gemini)
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
            "sector": info.get("sector", "Unknown"),
            "name": info.get("longName", symbol.upper())
        }
    except Exception as e:
        logger.error(f"Error fetching stock info for {symbol}: {e}")
        return None


def get_market_indices():
    """Get major market indices data."""
    indices = {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ",
        "^DJI": "Dow Jones",
        "^VIX": "VIX",
        "BTC-USD": "Bitcoin",
        "ETH-USD": "Ethereum"
    }
    result = {}
    for symbol, name in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                change = float(hist["Close"].iloc[-1] - hist["Open"].iloc[0])
                change_pct = (change / hist["Open"].iloc[0]) * 100 if hist["Open"].iloc[0] != 0 else 0
                result[name] = {
                    "symbol": symbol,
                    "price": price,
                    "change": change,
                    "change_percent": change_pct
                }
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
    return result


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


@app.route('/api/market/indices')
def market_indices():
    """Get major market indices."""
    data = get_market_indices()
    return jsonify(data), 200


@app.route('/api/search/<query>')
def search_stocks(query):
    """Search for stocks matching query."""
    try:
        # Get a list of popular stocks
        popular = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "VTI", "BTC-USD", "ETH-USD", "SOL-USD"]
        results = []
        for symbol in popular:
            if query.upper() in symbol:
                info = get_stock_info(symbol)
                if info:
                    results.append(info)
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify([]), 200


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
    symbol = data.get('symbol', 'AAPL').upper()
    
    try:
        # Get real stock data
        stock_info = get_stock_info(symbol)
        price_info = ""
        if stock_info:
            price_info = f"Current price: ${stock_info.get('price', 'N/A')}, Change: {stock_info.get('change_percent', 0):.2f}%"
        
        response = gemini_model.generate_content(
            f"Provide a brief investment analysis of {symbol} stock. "
            f"{price_info} "
            f"Include: Current sentiment (Bullish/Bearish/Neutral), "
            f"Key strengths, Key risks, Short-term outlook, Long-term outlook. "
            f"Keep response under 200 words."
        )
        return jsonify({
            "symbol": symbol,
            "analysis": response.text,
            "price_info": price_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Gemini analysis error: {e}")
        return jsonify({"error": str(e)}), 500


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
