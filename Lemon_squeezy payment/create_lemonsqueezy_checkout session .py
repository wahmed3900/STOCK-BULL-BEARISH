@app.route('/create-checkout-session', methods=['POST'])
@require_auth
def create_lemonsqueezy_checkout():
    try:
        headers = {
            'Accept': 'application/vnd.api+json',
            'Content-Type': 'application/vnd.api+json',
            'Authorization': f'Bearer {LEMON_SQUEEZY_API_KEY}'
        }

        payload = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "store_id": LEMON_SQUEEZY_STORE_ID,
                    "variant_id": LEMON_SQUEEZY_VARIANT_ID,
                    "checkout_data": {
                        "custom": {
                            "user_id": session.get('user_id')
                        }
                    }
                }
            }
        }

        response = requests.post(
            'https://api.lemonsqueezy.com/v1/checkouts',
            headers=headers,
            json=payload
        )
        response.raise_for_status()

        # Extract the hosted payment URL
        checkout_url = response.json()['data']['attributes']['url']

        # Return the URL so your frontend can redirect to it
        return jsonify({'checkout_url': checkout_url}), 200

    except Exception as e:
        logger.error("checkout_error", error=str(e))
        return jsonify({'error': 'Failed to create checkout session'}), 400