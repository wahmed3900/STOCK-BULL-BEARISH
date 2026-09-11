@app.route('/webhook', methods=['POST'])
def lemonsqueezy_webhook():
    payload = request.get_data()
    signature = request.headers.get('X-Signature')

    # Verify the webhook signature
    if not signature or not LEMON_SQUEEZY_WEBHOOK_SECRET:
        return '', 400

    computed_signature = hmac.new(
        LEMON_SQUEEZY_WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        logger.warning("webhook_signature_invalid")
        return '', 401

    event = request.json
    event_name = event.get('meta', {}).get('event_name')

    if event_name == 'order_created':
        # Extract user_id from the custom data you passed earlier
        custom_data = event.get('data', {}).get('attributes', {}).get('custom_data', {})
        user_id = custom_data.get('user_id')

        if user_id:
            # TODO: Update your user's tier in your database/session
            # Example: session['tier'] = 'premium' (but session is per-user,
            # you likely want to store this in a database tied to user_id)
            logger.info("user_upgraded_to_premium", user_id=user_id)
            # If you have a DB: db.update_user_tier(user_id, 'premium')

    return '', 200