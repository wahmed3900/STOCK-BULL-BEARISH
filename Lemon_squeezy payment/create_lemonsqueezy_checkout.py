@app.route('/create-checkout-session', methods=['POST'])
@require_auth
def create_lemonsqueezy_checkout():
    try:
        headers = {
            'Accept': 'application/vnd.api+json',
            'Content-Type': 'application/vnd.api+json',
            'Authorization': f'Bearer {LEMON_SQUEEZY_API_KEY}'
        }
        data = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "variant_id": LEMON_SQUEEZY_VARIANT_ID,
                    "checkout_data": {
                        "email": session.get('user_email', 'customer@example.com'),
                        "custom": {"user_id": session.get('user_id')}
                    }
                }
            }
        }
        response = requests.post('https://api.lemonsqueezy.com/v1/checkouts', headers=headers, json=data)
        response.raise_for_status()
        checkout_url = response.json()['data']['attributes']['url']
        return jsonify({'checkout_url': checkout_url}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400