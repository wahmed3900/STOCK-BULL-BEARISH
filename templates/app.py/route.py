@app.route("/premium/analysis")
def premium_analysis():
    if not is_subscriber("starter"):
        return jsonify({"error": "Upgrade required"}), 403

    symbol = request.args.get("symbol")
    model = request.args.get("model", "openrouter/free")

    return jsonify({"analysis": f"Advanced analysis for {symbol} using {model}"})
