from flask import Flask, Response, render_template
from services.streaming import stream_multi_model
import yfinance as yf
import os

app = Flask(__name__)


def fetch_latest_news(symbol: str) -> str:
    ticker = yf.Ticker(symbol)
    info = ticker.info
    return f"Company: {info.get('longName', symbol)} | Sector: {info.get('sector', 'N/A')}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stream/<symbol>")
def stream(symbol):
    news = fetch_latest_news(symbol)

    def generate():
        yield from stream_multi_model(symbol, news)

    return Response(generate(), mimetype="text/event-stream")


# ⭐ REQUIRED FOR RENDER — DO NOT REMOVE
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
