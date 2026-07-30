"""
MongoDB persistence for the dashboard.
Single-user MVP: one watchlist collection, one settings doc for tier.
Swap this for a per-user schema once you add auth/Stripe.

Works with either local MongoDB (mongodb://localhost:27017) or a free
MongoDB Atlas cluster - just set MONGODB_URI in your .env.
"""
import os
from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "stock_dashboard")

FREE_TIER_LIMIT = 3

_client = MongoClient(MONGODB_URI)
_db = _client[DB_NAME]
_watchlist = _db["watchlist"]
_settings = _db["settings"]


def init_db():
    _watchlist.create_index("ticker", unique=True)
    if _settings.find_one({"_id": "tier"}) is None:
        _settings.insert_one({"_id": "tier", "value": "free"})


def get_tier():
    doc = _settings.find_one({"_id": "tier"})
    return doc["value"] if doc else "free"


def set_tier(tier: str):
    _settings.update_one({"_id": "tier"}, {"$set": {"value": tier}}, upsert=True)


def get_watchlist():
    docs = _watchlist.find().sort("added_at", 1)
    return [d["ticker"] for d in docs]


def add_ticker(ticker: str):
    from datetime import datetime, timezone
    _watchlist.update_one(
        {"ticker": ticker.upper()},
        {"$setOnInsert": {"ticker": ticker.upper(), "added_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def remove_ticker(ticker: str):
    _watchlist.delete_one({"ticker": ticker.upper()})
