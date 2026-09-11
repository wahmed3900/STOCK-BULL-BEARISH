from flask import Flask, jsonify
import yfinance as yf  # for stock data
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "Stock Bull-Bearish Bot",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/api/stock/<symbol>')
def get_stock(symbol):
    try:
        stock = yf.Ticker(symbol.upper())
        info = stock.info
        return jsonify({
            "symbol": symbol.upper(),
            "price": info.get('regularMarketPrice'),
            "change": info.get('regularMarketChangePercent'),
            "volume": info.get('volume')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
