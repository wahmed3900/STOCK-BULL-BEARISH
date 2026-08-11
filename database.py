"""
MongoDB persistence for the dashboard.
Single-user MVP: one watchlist collection, one settings doc for tier.
"""
import os
import logging
from datetime import datetime, timezone
from typing import List, Optional
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ConnectionFailure
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "stock_dashboard")
FREE_TIER_LIMIT = 3

# Connection pool settings for Render
CONNECTION_TIMEOUT_MS = int(os.environ.get("MONGODB_TIMEOUT", 30000))
MAX_POOL_SIZE = int(os.environ.get("MONGODB_MAX_POOL_SIZE", 10))

# In-memory fallback when MongoDB is unavailable
_fallback_settings = {"tier": "free"}
_fallback_watchlist = set()
_db_available = True

# Initialize client with proper settings
_client = MongoClient(
    MONGODB_URI,
    server_api=ServerApi('1'),  # For MongoDB Atlas
    connectTimeoutMS=CONNECTION_TIMEOUT_MS,
    socketTimeoutMS=CONNECTION_TIMEOUT_MS,
    maxPoolSize=MAX_POOL_SIZE,
    minPoolSize=1,
    maxIdleTimeMS=60000,  # Close idle connections after 60 seconds
)

_db = _client[DB_NAME]
_watchlist = _db["watchlist"]
_settings = _db["settings"]


def _safe_db_call(action, default=None):
    """Execute DB operation with fallback to in-memory storage."""
    global _db_available
    try:
        result = action()
        _db_available = True
        return result
    except (PyMongoError, ConnectionFailure) as e:
        logger.warning(f"MongoDB operation failed: {e}")
        _db_available = False
        return default
    except Exception as e:
        logger.error(f"Unexpected error in DB operation: {e}")
        return default


def check_connection() -> bool:
    """Check if MongoDB is reachable."""
    def action():
        _client.admin.command('ping')
        return True
    return _safe_db_call(action, default=False) or _db_available


def init_db():
    """Initialize database with indexes and default settings."""
    def action():
        # Create unique index on ticker
        _watchlist.create_index("ticker", unique=True)
        # Create index for sorting
        _watchlist.create_index("added_at")
        
        # Ensure settings document exists
        if _settings.find_one({"_id": "tier"}) is None:
            _settings.insert_one({"_id": "tier", "value": "free"})
        
        logger.info("Database initialized successfully")
        return True

    return _safe_db_call(action, default=False)


def get_tier() -> str:
    """Get current user tier (free/pro)."""
    def action():
        doc = _settings.find_one({"_id": "tier"})
        return doc["value"] if doc else "free"
    
    result = _safe_db_call(action)
    if result is None:
        logger.debug("Using fallback tier")
        return _fallback_settings["tier"]
    return result


def set_tier(tier: str):
    """Set user tier."""
    def action():
        _settings.update_one(
            {"_id": "tier"}, 
            {"$set": {"value": tier}}, 
            upsert=True
        )
        return True
    
    success = _safe_db_call(action, default=False)
    if not success:
        _fallback_settings["tier"] = tier


def get_watchlist() -> List[str]:
    """Get all tickers in watchlist."""
    def action():
        docs = _watchlist.find().sort("added_at", 1)
        return [d["ticker"] for d in docs]
    
    result = _safe_db_call(action)
    if result is None:
        logger.debug("Using fallback watchlist")
        return sorted(_fallback_watchlist)
    return result


def add_ticker(ticker: str) -> bool:
    """Add a ticker to watchlist."""
    def action():
        result = _watchlist.update_one(
            {"ticker": ticker.upper()},
            {"$setOnInsert": {
                "ticker": ticker.upper(), 
                "added_at": datetime.now(timezone.utc)
            }},
            upsert=True,
        )
        return result.upserted_id is not None or result.modified_count > 0
    
    success = _safe_db_call(action, default=False)
    if not success:
        _fallback_watchlist.add(ticker.upper())
        return True  # Fallback succeeded
    return success


def remove_ticker(ticker: str) -> bool:
    """Remove a ticker from watchlist."""
    def action():
        result = _watchlist.delete_one({"ticker": ticker.upper()})
        return result.deleted_count > 0
    
    success = _safe_db_call(action, default=False)
    if not success:
        _fallback_watchlist.discard(ticker.upper())
        return True  # Fallback succeeded
    return success


def get_watchlist_count() -> int:
    """Get number of tickers in watchlist."""
    def action():
        return _watchlist.count_documents({})
    return _safe_db_call(action, default=len(_fallback_watchlist))


def clear_watchlist() -> bool:
    """Clear all tickers from watchlist."""
    def action():
        result = _watchlist.delete_many({})
        return result.deleted_count > 0
    return _safe_db_call(action, default=False)


def is_pro_user() -> bool:
    """Check if user has pro tier."""
    return get_tier() == "pro"


def can_add_stock() -> bool:
    """Check if user can add more stocks (respects tier limits)."""
    tier = get_tier()
    if tier == "pro":
        return True
    
    count = get_watchlist_count()
    return count < FREE_TIER_LIMIT


# Optional: Export for use in Flask
__all__ = [
    'init_db',
    'get_tier',
    'set_tier',
    'get_watchlist',
    'add_ticker',
    'remove_ticker',
    'get_watchlist_count',
    'clear_watchlist',
    'is_pro_user',
    'can_add_stock',
    'check_connection',
    'FREE_TIER_LIMIT',
    '_db_available',
]
