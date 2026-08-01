

from flask import Response
import time
import json

START_TIME = time.time()

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import database as db
from services.stock_data import get_quote
from services.sentiment import get_sentiment

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"
db.init_db()

@app.route("/")
def index():
    tickers = db.get_watchlist()
    tier = db.get_tier()
    quotes = []

    for ticker in tickers:
        quote = get_quote(ticker)
        if quote:
            if tier == "pro":
                quote["sentiment"] = get_sentiment(ticker, quote["price"], quote["change"], quote["change_pct"])
            else:
                quote["sentiment"] = {"verdict": "Locked", "reason": "Upgrade to Pro for AI analysis."}
            quotes.append(quote)
        else:
            quotes.append({
                "ticker": ticker,
                "price": None,
                "change": None,
                "change_pct": None,
                "source": "unavailable",
                "sentiment": {"verdict": "N/A", "reason": ""}
            })

    return render_template(
        "index.html",
        quotes=quotes,
        tier=tier,
        limit=db.FREE_TIER_LIMIT,
        at_limit=(tier == "free" and len(tickers) >= db.FREE_TIER_LIMIT),
    )

@app.route("/add", methods=["POST"])
def add_stock():
    ticker = request.form.get("ticker", "").strip().upper()
    tier = db.get_tier()
    watchlist = db.get_watchlist()

    if not ticker:
        flash("Enter a ticker symbol.", "error")
    elif ticker in watchlist:
        flash(f"{ticker} is already on your watchlist.", "error")
    elif tier == "free" and len(watchlist) >= db.FREE_TIER_LIMIT:
        flash(f"Free tier is limited to {db.FREE_TIER_LIMIT} stocks. Upgrade to add more.", "error")
    else:
        quote = get_quote(ticker)
        if not quote:
            flash(f"Couldn't find price data for '{ticker}'. Check the symbol.", "error")
        else:
            db.add_ticker(ticker)
            flash(f"Added {ticker}.", "success")
    return redirect(url_for("index"))

@app.route("/remove/<ticker>", methods=["POST"])
def remove_stock(ticker):
    db.remove_ticker(ticker)
    flash(f"Removed {ticker.upper()}.", "success")
    return redirect(url_for("index"))

@app.route("/analyze/<ticker>")
def analyze(ticker):
    if db.get_tier() != "pro":
        return jsonify({"verdict": "Locked", "reason": "Upgrade to Pro for AI analysis."}), 403
    quote = get_quote(ticker)
    if not quote or quote["price"] is None:
        return jsonify({"verdict": "Error", "reason": "No price data available."}), 400
    result = get_sentiment(ticker, quote["price"], quote["change"], quote["change_pct"])
    return jsonify(result)

@app.route("/upgrade", methods=["POST"])
def upgrade():
    db.set_tier("pro")
    flash("Upgraded to Pro (demo - no payment was processed).", "success")
    return redirect(url_for("index"))

@app.route("/downgrade", methods=["POST"])
def downgrade():
    db.set_tier("free")
    flash("Back to Free tier.", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)

# ---- /api/health ----
@app.route("/api/health")
def api_health():
    try:
        watchlist = db.get_watchlist()
        db_ok = True
    except Exception:
        watchlist = []
        db_ok = False
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "uptime_seconds": int(time.time() - START_TIME),
        "database": db_ok,
        "watchlist_count": len(watchlist),
    }), (200 if db_ok else 503)


# ---- /api/model ----
@app.route("/api/model")
def api_model():
    test_quote = get_quote("AAPL")
    if not test_quote:
        return jsonify({"status": "down", "reason": "quote source unavailable"}), 503
    try:
        result = get_sentiment("AAPL", test_quote["price"], test_quote["change"], test_quote["change_pct"])
        return jsonify({"status": "ok", "sample_verdict": result.get("verdict")}), 200
    except Exception as e:
        return jsonify({"status": "down", "reason": str(e)}), 503


# ---- /stream/<ticker> ----
@app.route("/stream/<ticker>")
def stream(ticker):
    ticker = ticker.strip().upper()
    def event_stream():
        for _ in range(60):
            quote = get_quote(ticker)
            yield f"data: {json.dumps(quote or {'error': 'no data'})}\n\n"
            time.sleep(5)
    return Response(event_stream(), mimetype="text/event-stream")
