"""
MongoDB persistence for the Bull/Bear Dashboard.
Single-user MVP: one watchlist collection + one settings doc for tier.

Works with either:
- Local MongoDB (mongodb://localhost:27017)
- MongoDB Atlas (mongodb+srv://...)
"""

import os
from pymongo import MongoClient

# Free tier limit
FREE_TIER_LIMIT = 3

# Read environment variables
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "stock_dashboard")

# Connect to MongoDB
_client = MongoClient(MONGODB_URI)
_db = _client[DB_NAME]

# Collections
_watchlist = _db["watchlist"]
_settings = _db["settings"]


def init_db():
    """
    Initialize DB:
    - Create unique index on ticker
    - Ensure tier doc exists
    """
    try:
        _watchlist.create_index("ticker", unique=True)
    except Exception:
        pass  # Index may already exist

    # Ensure tier doc exists
    if _settings.find_one({"_id": "tier"}) is None:
        _settings.insert_one({"_id": "tier", "value": "free"})


def get_tier():
    """
    Returns: "free" or "pro"
    """
    doc = _settings.find_one({"_id": "tier"})
    return doc["value"] if doc else "free"


def set_tier(tier: str):
    """
    Sets tier to "free" or "pro"
    """
    _settings.update_one(
        {"_id": "tier"},
        {"$set": {"value": tier}},
        upsert=True
    )


def get_watchlist():
    """
    Returns list of tickers sorted by insertion time.
    """
    docs = _watchlist.find().sort("added_at", 1)
    return [d["ticker"] for d in docs]


def add_ticker(ticker: str):
    """
    Adds ticker to watchlist (safe upsert).
    """
    from datetime import datetime, timezone

    _watchlist.update_one(
        {"ticker": ticker.upper()},
        {
            "$setOnInsert": {
                "ticker": ticker.upper(),
                "added_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )


def remove_ticker(ticker: str):
    """
    Removes ticker from watchlist.
    """
    _watchlist.delete_one({"ticker": ticker.upper()})
