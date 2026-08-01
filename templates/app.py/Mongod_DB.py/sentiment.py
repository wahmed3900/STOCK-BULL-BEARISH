from database import sentiment_history
from datetime import datetime

@app.route("/sentiment")
def sentiment():
    symbol = request.args.get("symbol")
    model = request.args.get("model", "openrouter/free")

    # Fake sentiment for now
    sentiment = "Bullish"
    confidence = 78

    sentiment_history.insert_one({
        "user_id": 1,
        "symbol": symbol,
        "sentiment": sentiment,
        "confidence": confidence,
        "timestamp": datetime.utcnow()
    })

    return jsonify({
        "symbol": symbol,
        "sentiment": sentiment,
        "confidence": confidence
    })
