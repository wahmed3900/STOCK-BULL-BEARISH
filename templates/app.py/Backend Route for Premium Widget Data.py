@app.route("/premium/widgets")
def premium_widgets():
    if not is_subscriber("starter"):
        return jsonify({"error": "Upgrade required"}), 403

    return jsonify({
        "confidence": 78,
        "heatmap": [1, -1, 1, 1, -1],
        "risk": [60, 40, 70, 50, 80],
        "sentiment": [
            {"symbol": "AAPL", "sentiment": "Bullish"},
            {"symbol": "TSLA", "sentiment": "Bearish"},
            {"symbol": "NVDA", "sentiment": "Bullish"}
        ]
    })
