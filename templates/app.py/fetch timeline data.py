@app.route("/premium/sentiment-timeline")
def sentiment_timeline():
    if not is_subscriber("pro"):
        return jsonify({"error": "Pro tier required"}), 403

    symbol = request.args.get("symbol")
    user_id = 1

    history = list(
        sentiment_history.find({"user_id": user_id, "symbol": symbol})
        .sort("timestamp", 1)
    )

    return jsonify({"timeline": history})
