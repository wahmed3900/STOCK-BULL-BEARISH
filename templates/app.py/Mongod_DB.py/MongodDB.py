@app.route("/upgrade")
def upgrade():
    tier = request.args.get("tier")
    users.update_one({"id": 1}, {"$set": {"subscription": tier}})
    return jsonify({"message": f"Subscription upgraded to {tier}!"})
