@app.route("/success")
def success():
    session_id = request.args.get("session_id")
    session = stripe.checkout.Session.retrieve(session_id)

    user_id = session.metadata["user_id"]
    subscription_tier = session.display_items[0].price.product

    users.update_one(
        {"id": int(user_id)},
        {"$set": {"subscription": subscription_tier}}
    )

    return "Subscription activated! You can close this page."
