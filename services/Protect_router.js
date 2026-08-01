@app.route("/premium/analysis")
def premium_analysis():
    if not is_subscriber(current_user.id):
        return jsonify({"error": "Upgrade required"}), 403
