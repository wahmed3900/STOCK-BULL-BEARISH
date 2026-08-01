if not is_subscriber("starter"):
    return jsonify({"error": "Upgrade required"}), 403

    