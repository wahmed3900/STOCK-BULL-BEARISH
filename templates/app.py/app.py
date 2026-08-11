# stock-dashboard/app.py
import os
import json
import time
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from flask_cors import CORS
from google import genai
import yfinance as yf

# Load .env values
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Load Gemini key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash-lite"


def fetch_ohlc(symbol, period="1mo", interval="1d"):
    """Pull OHLC candles from yfinance and shape them for the Plotly frontend."""
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


@app.route('/', methods=['GET'])
@app.route('/dashboard', methods=['GET'])
def dashboard():
    return render_template('index.html')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "gemini_configured": True,
        "routes": [
            "/", "/dashboard", "/health",
            "/api/analyze/<ticker>", "/stream/<symbol>", "/chart"
        ]
    }), 200


# -----------------------------
# Candlestick chart data
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
        return jsonify({"error": str(exc)}), 500


# -----------------------------
# Gemini Stock Analysis Endpoint
# -----------------------------
@app.route('/api/analyze/<ticker>', methods=['GET'])
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
        return jsonify({"status": "error", "message": str(exc)}), 500


# -----------------------------
# Gemini + Price Streaming SSE
# -----------------------------
@app.route('/stream/<symbol>', methods=['GET'])
def stream_ticker(symbol):
    symbol = symbol.strip().upper()

    def generate():
        last_price = None
        while True:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='1d', interval='1m')
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


@app.errorhandler(404)
def not_found(_error):
    return jsonify({
        "error": "Route not found",
        "available_routes": [
            "/", "/dashboard", "/health",
            "/api/analyze/<ticker>", "/stream/<symbol>", "/chart"
        ]
    }), 404


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='127.0.0.1', port=port, debug=True)
