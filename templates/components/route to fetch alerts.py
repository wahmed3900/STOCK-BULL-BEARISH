@app.route("/premium/alerts")
def get_alerts():
    if not is_subscriber("pro"):
        return jsonify({"error": "Pro tier required"}), 403

    user_id = 1
    user_alerts = list(alerts.find({"user_id": user_id}).sort("timestamp", -1))

    return jsonify({"alerts": user_alerts})
