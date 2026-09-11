@app.route('/stripe-webhook', methods=['POST']) # Keep same endpoint or rename to /webhook
def lemonsqueezy_webhook():
    payload = request.get_data()
    signature = request.headers.get('X-Signature')
    secret = LEMON_SQUEEZY_WEBHOOK_SECRET
    # Verification omitted for brevity but use hmac.compare_digest
    event = request.json
    if event['meta']['event_name'] == 'order_created':
        user_id = event['data']['attributes']['custom_data'].get('user_id')
        # Upgrade user to premium
    return '', 200