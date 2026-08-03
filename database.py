"""
MongoDB persistence for the dashboard.
Single-user MVP: one watchlist collection, one settings doc for tier.
Swap this for a per-user schema once you add auth/Stripe.

Works with either local MongoDB (mongodb://localhost:27017) or a free
MongoDB Atlas cluster - just set MONGODB_URI in your .env.
"""
import os
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "stock_dashboard")

FREE_TIER_LIMIT = 3

_client = MongoClient(MONGODB_URI)
_db = _client[DB_NAME]
_watchlist = _db["watchlist"]
_settings = _db["settings"]

_fallback_settings = {"tier": "free"}
_fallback_watchlist = set()


def _safe_db_call(action, default=None):
    try:
        return action()
    except PyMongoError:
        return default
    except Exception:
        return default


def init_db():
    def action():
        _watchlist.create_index("ticker", unique=True)
        if _settings.find_one({"_id": "tier"}) is None:
            _settings.insert_one({"_id": "tier", "value": "free"})
        return True

    return _safe_db_call(action, default=False)


def get_tier():
    def action():
        doc = _settings.find_one({"_id": "tier"})
        return doc["value"] if doc else "free"

    result = _safe_db_call(action)
    if result is None:
        return _fallback_settings["tier"]
    return result


def set_tier(tier: str):
    def action():
        _settings.update_one({"_id": "tier"}, {"$set": {"value": tier}}, upsert=True)
        return True

    success = _safe_db_call(action, default=False)
    if not success:
        _fallback_settings["tier"] = tier


def get_watchlist():
    def action():
        docs = _watchlist.find().sort("added_at", 1)
        return [d["ticker"] for d in docs]

    result = _safe_db_call(action)
    if result is None:
        return sorted(_fallback_watchlist)
    return result


def add_ticker(ticker: str):
    from datetime import datetime, timezone
    def action():
        _watchlist.update_one(
            {"ticker": ticker.upper()},
            {"$setOnInsert": {"ticker": ticker.upper(), "added_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return True

    success = _safe_db_call(action, default=False)
    if not success:
        _fallback_watchlist.add(ticker.upper())


def remove_ticker(ticker: str):
    def action():
        _watchlist.delete_one({"ticker": ticker.upper()})
        return True

    success = _safe_db_call(action, default=False)
    if not success:
        _fallback_watchlist.discard(ticker.upper())
