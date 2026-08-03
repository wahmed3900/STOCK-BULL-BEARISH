import os

from flask import Flask, flash, redirect, render_template, request, url_for

from database import get_tier, init_db, set_tier
from services.sentiment import get_sentiment
from services.stock_data import get_quote

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

try:
    init_db()
except Exception:
    pass


def analyze_ticker(ticker: str):
    quote = get_quote(ticker)
    if not quote:
        return None

    sentiment = get_sentiment(
        quote["ticker"], quote["price"], quote["change"], quote["change_pct"]
    )

    return {
        "ticker": quote["ticker"],
        "price": quote["price"],
        "sentiment": sentiment["verdict"],
        "summary": sentiment["reason"],
        "source": quote.get("source", "unknown"),
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", tier=get_tier())


@app.route("/analyze", methods=["POST"])
def analyze():
    ticker = request.form.get("ticker", "").strip()
    if not ticker:
        flash("Enter a stock ticker like AAPL, TSLA, or NVDA.")
        return redirect(url_for("index"))

    result = analyze_ticker(ticker)
    if not result:
        flash("Could not retrieve quote data for that ticker. Please try a different symbol.")
        return redirect(url_for("index"))

    return render_template("index.html", result=result, tier=get_tier())


@app.route("/reanalyze", methods=["POST"])
def reanalyze():
    ticker = request.form.get("ticker", "").strip()
    if not ticker:
        flash("Missing ticker for re-analysis.")
        return redirect(url_for("index"))

    result = analyze_ticker(ticker)
    if not result:
        flash("Could not retrieve quote data for that ticker. Please try again.")
        return redirect(url_for("index"))

    return render_template("index.html", result=result, tier=get_tier())


@app.route("/pricing", methods=["GET"])
def pricing():
    return render_template("pricing.html", tier=get_tier())


@app.route("/upgrade", methods=["POST"])
def upgrade():
    tier = request.form.get("tier", "free")
    if tier not in {"free", "starter", "pro"}:
        tier = "free"

    set_tier(tier)
    flash(f"Subscription tier updated to {tier.title()}.")
    return redirect(url_for("pricing"))


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200


@app.route("/api/health", methods=["GET"])
def api_health():
    return {"status": "ok"}, 200


# register streaming blueprints
try:
    from services import streaming as streaming_mod
    app.register_blueprint(streaming_mod.bp)
except Exception:
    pass

try:
    from services.services import endpoint as endpoint_mod
    app.register_blueprint(endpoint_mod.bp)
except Exception:
    pass


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
