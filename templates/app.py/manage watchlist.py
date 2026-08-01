@app.route("/premium/watchlist", methods=["POST"])
def add_to_watchlist():
    if not is_subscriber("pro"):
        return jsonify({"error": "Pro tier required"}), 403

    symbol = request.json.get("symbol")
    user_id = 1

    watchlist.update_one(
        {"user_id": user_id},
        {"$addToSet": {"symbols": symbol}},
        upsert=True
    )

    return jsonify({"message": f"{symbol} added to watchlist"})
