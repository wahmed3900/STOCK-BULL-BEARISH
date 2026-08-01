import stripe
import os

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def create_checkout_session(price_id, user_id):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url="http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="http://localhost:5000/pricing",
        metadata={"user_id": user_id}
    )
    return session.url
