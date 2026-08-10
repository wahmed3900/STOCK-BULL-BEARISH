import os
import json
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
import yfinance as yf
import google.generativeai as genai

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Configure GenAI
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel("gemini-3.6-flash")
except Exception as e:
    print(f"Initialization error: {e}")
    genai = None
    gemini_model = None


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


# Root route -> renders the dashboard, not raw JSON
@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')


# Health check route
@app.route('/health', methods=['GET'])
def health():
    if genai is None:
        return jsonify({"status": "error", "message": "GenAI not configured"}), 500
    return jsonify({"status": "environment_active", "model": "gemini-3.6-flash"})


# Chart data for Plotly candlestick — this is what loadChart() in frontend.js calls
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Analyze endpoint — this is what the "Analyze" button form submits to
@app.route('/analyze', methods=['POST'])
def analyze():
    symbol = (request.form.get('symbol') or request.form.get('ticker') or '').strip().upper()
    if not symbol:
        return jsonify({"error": "No ticker provided"}), 400

    try:
        ohlc = fetch_ohlc(symbol, period="1mo", interval="1d")
    except Exception as e:
        return jsonify({"error": f"Failed to fetch price data: {e}"}), 500

    if not ohlc:
        return jsonify({"error": f"No price data found for {symbol}"}), 404

    summary = "AI analysis unavailable."
    if gemini_model:
        try:
            recent = ohlc[-10:]
            prompt = (
                f"You are a market analyst. Given this recent OHLC price data for {symbol}: "
                f"{json.dumps(recent)}, give a short bullish/bearish verdict and a 2-3 sentence "
                f"rationale in plain language."
            )
            response = gemini_model.generate_content(prompt)
            summary = response.text
        except Exception as e:
            summary = f"AI analysis failed: {e}"

    return jsonify({
        "symbol": symbol,
        "summary": summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
