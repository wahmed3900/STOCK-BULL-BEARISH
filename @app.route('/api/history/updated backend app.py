# stock-dashboard/app.py
import os
import json
import time
import logging
from datetime import datetime, timezone

import structlog
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
import yfinance as yf

# Load .env values
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Structured logging
structlog.configure(
    processors=[structlog.processors.JSONRenderer()]
)
logger = structlog.get_logger()

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Gemini client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash-lite"


def fetch_ohlc(symbol, period="1mo", interval="1d"):
    """Pull OHLC candles from yfinance and shape them for the Plotly frontend."""
    ticker_obj = yf.Ticker(symbol)
    hist = ticker_obj.history(period=period, interval=interval)
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


# -----------------------------
# Pages
# -----------------------------
@app.route('/', methods=['GET'])
@app.route('/dashboard', methods=['GET'])
def dashboard():
    return render_template('index.html')


# -----------------------------
# Health / status
# -----------------------------
@app.route('/health', methods=['GET', 'HEAD'])
@app.route('/api/health', methods=['GET', 'HEAD'])
def health_check():
    """Health check endpoint for uptime monitoring"""
    return jsonify({
        'status': 'healthy',
        'gemini_configured': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'service': 'stock-bull-bearish'
    }), 200


def check_mongodb():
    try:
        # Plug in your real MongoDB connection check here
        return 'not_configured'
    except Exception:
        return 'disconnected'


def check_redis():
    try:
        # Plug in your real Redis connection check here
        return 'not_configured'
    except Exception:
        return 'disconnected'


def check_yfinance():
    try:
        test = yf.Ticker("AAPL")
        _ = test.info
        return 'available'
    except Exception:
        return 'unavailable'


@app.route('/api/status', methods=['GET', 'HEAD'])
def full_status():
    """Comprehensive service status"""
    return jsonify({
        'service': 'stock-bull-bearish',
        'version': '1.0.0',
        'status': 'operational',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'endpoints': {
            'health': '/health',
            'analyze': '/api/analyze/<ticker>',
            'chart': '/chart',
            'stream': '/stream/<symbol>',
            'history': '/api/history/<ticker>',
            'quote': '/api/quote/<ticker>',
            'model': '/api/model',
        },
        'dependencies': {
            'mongodb': check_mongodb(),
            'redis': check_redis(),
            'yfinance': check_yfinance()
        }
    }), 200


@app.route('/api/model', methods=['GET', 'HEAD'])
@limiter.limit("10 per minute")
def get_model_info():
    """Get information about the ML/AI model in use"""
    try:
        model_info = {
            'status': 'available',
            'model': MODEL,
            'provider': 'google-genai',
            'purpose': 'stock sentiment + market analysis',
        }
        return jsonify(model_info), 200
    except Exception as exc:
        logger.error("model_endpoint_error", error=str(exc))
        return jsonify({'error': 'Model unavailable'}), 503


# -----------------------------
# Candlestick chart data (Plotly)
# -----------------------------
@app.route('/chart', methods=['GET'])
def chart():
    symbol = request.args.get('symbol', 'AAPL').strip().upper()
    period = request.args.get('period', '1mo')
    interval = request.args.get('interval', '1d')

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    try:
        ohlc = fetch_ohlc(symbol, period, interval)
        if not ohlc:
            return jsonify({"error": f"No chart data found for {symbol}"}), 404
        return jsonify({"symbol": symbol, "period": period, "interval": interval, "ohlc": ohlc})
    except Exception as exc:
        logger.error("chart_error", ticker=symbol, error=str(exc))
        return jsonify({"error": str(exc)}), 500


# -----------------------------
# Raw historical data (fuller columns than /chart)
# -----------------------------
@app.route('/api/history/<ticker>', methods=['GET', 'HEAD'])
@limiter.limit("30 per minute")
def get_history(ticker):
    """Get historical data for a ticker"""
    try:
        days = request.args.get('days', 30, type=int)

        if days <= 0 or days > 365:
            return jsonify({
                'error': 'Invalid days parameter',
                'message': 'Days must be between 1 and 365'
            }), 400

        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period=f'{days}d')

        if hist.empty:
            return jsonify({
                'error': 'No data found',
                'message': f'No historical data available for {ticker}'
            }), 404

        hist_dict = hist.reset_index().to_dict('records')
        for record in hist_dict:
            record['Date'] = record['Date'].isoformat()

        return jsonify({
            "ticker": ticker.upper(),
            "history": hist_dict,
            "count": len(hist_dict),
            "days": days
        }), 200

    except Exception as exc:
        logger.error("history_error", ticker=ticker, error=str(exc))
        return jsonify({
            'error': 'History retrieval failed',
            'message': str(exc)
        }), 503


# -----------------------------
# One-shot price/volume snapshot
# (renamed from /stream/<ticker> to avoid clashing with the real SSE stream below)
# -----------------------------
@app.route('/api/quote/<ticker>', methods=['GET', 'HEAD'])
@limiter.limit("30 per minute")
def get_quote(ticker):
    """Single JSON snapshot of current price/volume — not a live stream"""
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info

        current_price = info.get('regularMarketPrice', info.get('currentPrice', 0))
        previous_close = info.get('regularMarketPreviousClose', info.get('previousClose', current_price))

        change = ((current_price - previous_close) / previous_close * 100) if previous_close else 0

        data = {
            'ticker': ticker.upper(),
            'price': current_price,
            'change': round(change, 2),
            'volume': info.get('regularMarketVolume', 0),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        return jsonify(data), 200
    except Exception as exc:
        logger.error("quote_error", ticker=ticker, error=str(exc))
        return jsonify({'error': 'Quote unavailable'}), 503


# -----------------------------
# Gemini stock sentiment analysis
# -----------------------------
@app.route('/api/analyze/<ticker>', methods=['GET'])
@limiter.limit("20 per minute")
def analyze_stock(ticker):
    try:
        prompt = (
            f"Provide a concise market and sentiment analysis for {ticker.upper()}. "
            "Include catalysts, risks, and a bull/bear leaning."
        )
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        return jsonify({
            "ticker": ticker.upper(),
            "status": "success",
            "analysis": response.text,
        }), 200
    except Exception as exc:
        logger.error("analyze_error", ticker=ticker, error=str(exc))
        return jsonify({"status": "error", "message": str(exc)}), 500


# -----------------------------
# Gemini + live price streaming (SSE) — kept from the previous version
# -----------------------------
@app.route('/stream/<symbol>', methods=['GET'])
def stream_ticker(symbol):
    symbol = symbol.strip().upper()

    def generate():
        last_price = None
        while True:
            try:
                ticker_obj = yf.Ticker(symbol)
                hist = ticker_obj.history(period='1d', interval='1m')
                if not hist.empty and 'Close' in hist.columns:
                    current_price = float(hist['Close'].iloc[-1])
                else:
                    current_price = None

                if current_price is not None and current_price != last_price:
                    last_price = current_price
                    ai_prompt = f"Give a short real-time sentiment update for {symbol}."
                    ai_response = client.models.generate_content(
                        model=MODEL,
                        contents=ai_prompt
                    )
                    payload = {
                        "symbol": symbol,
                        "price": current_price,
                        "sentiment": ai_response.text,
                        "timestamp": int(time.time())
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                else:
                    yield f": keepalive {int(time.time())}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                break
            time.sleep(5)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no"
    }
    return Response(stream_with_context(generate()), headers=headers)


# -----------------------------
# Error handlers
# -----------------------------
@app.errorhandler(404)
def not_found(_error):
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested endpoint does not exist',
        'available_endpoints': [
            '/', '/dashboard', '/health', '/api/health', '/api/status',
            '/chart', '/api/history/<ticker>', '/api/quote/<ticker>',
            '/api/model', '/api/analyze/<ticker>', '/stream/<symbol>'
        ]
    }), 404


@app.errorhandler(429)
def rate_limit_handler(_error):
    return jsonify({
        'error': 'Rate Limit Exceeded',
        'message': 'Too many requests. Please try again later.'
    }), 429


@app.errorhandler(500)
def internal_error(error):
    logger.error("internal_server_error", error=str(error))
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred'
    }), 500


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
