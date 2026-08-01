from flask import Flask, request, jsonify, redirect
from services.stripe_service import create_checkout_session
from database import users

app = Flask(__name__)

@app.route("/create-checkout-session")
def create_checkout():
    tier = request.args.get("tier")
    user_id = 1  # Replace with real auth later

    price_map = {
        "starter": "price_12345",
        "pro": "price_67890"
    }

    checkout_url = create_checkout_session(price_map[tier], user_id)
    return redirect(checkout_url)
