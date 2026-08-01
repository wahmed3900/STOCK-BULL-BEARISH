@app.route("/sentiment")
def sentiment():
    symbol = request.args.get("symbol")
    model = request.args.get("model", "openrouter/free")

    return jsonify({"sentiment": f"Sentiment for {symbol} using {model}"})
