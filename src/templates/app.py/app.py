import os
import re
import json
import logging
import time
import requests
import hmac
import hashlib
from functools import wraps
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, Response, stream_with_context
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import structlog
from flask_swagger_ui import get_swaggerui_blueprint
from flask_wtf.csrf import CSRFProtect
from redis import Redis
from pymongo import MongoClient
from openai import OpenAI

# Load workspace environment configurations
load_dotenv()

# Configure structured JSON platform logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# =============================================================================
#                               Configuration
# =============================================================================

class Config:
    """Base application system configurations."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_default_fallback_secret_key_32_chars_minimum')
    
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'

    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', "200 per day;50 per hour")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', "memory://")

    CACHE_MAXSIZE = int(os.environ.get('CACHE_MAXSIZE', '10000'))
    CACHE_TTL = int(os.environ.get('CACHE_TTL', '300'))  # 5 minutes default

    # Database and Integration Endpoints
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/prod_fin_db')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    ALPHA_VANTAGE_API_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', 'demo')
    
    # Financial Market Parameters
    MAX_CONCURRENT_WORKERS = int(os.environ.get('MAX_CONCURRENT_WORKERS', '10'))
    STREAMING_CHUNK_SIZE = int(os.environ.get('STREAMING_CHUNK_SIZE', '1024'))

# =============================================================================
#                               Domain Models
# =============================================================================

class MarketTrend(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

@dataclass(frozen=True)
class FinancialMetric:
    ticker: str
    price: float
    pe_ratio: Optional[float]
    market_cap: float
    volume: int
    timestamp: float = datetime.now(timezone.utc).timestamp()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

# =============================================================================
#                          Infrastructure Core Clients
# =============================================================================

class DatabaseManager:
    """Manages secure operational infrastructure persistence states."""
    def __init__(self, uri: str):
        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self.db = self.client.get_default_database()
            logger.info("database_connected", database_name=self.db.name)
        except Exception as e:
            logger.critical("database_connection_failed", error=str(e))
            raise

    def save_metric(self, metric: FinancialMetric) -> bool:
        try:
            collection = self.db['market_metrics']
            result = collection.update_one(
                {"ticker": metric.ticker},
                {"$set": asdict(metric)},
                upsert=True
            )
            return result.acknowledged
        except Exception as e:
            logger.error("metric_persistence_error", ticker=metric.ticker, error=str(e))
            return False

    def get_metric(self, ticker: str) -> Optional[Dict[str, Any]]:
        try:
            return self.db['market_metrics'].find_one({"ticker": ticker.upper()}, {"_id": 0})
        except Exception as e:
            logger.error("metric_retrieval_error", ticker=ticker, error=str(e))
            return None

class RedisCacheManager:
    """Provides thread-safe caching primitives via Redis infrastructure."""
    def __init__(self, connection_uri: str):
        if connection_uri.startswith("memory://"):
            self.client = None
            self.local_cache = {}
            logger.warn("redis_disabled_using_in_memory_fallback")
        else:
            try:
                self.client = Redis.from_url(connection_uri, decode_responses=True)
                self.client.ping()
                logger.info("redis_connected")
            except Exception as e:
                logger.critical("redis_connection_failed", error=str(e))
                raise

    def get(self, key: str) -> Optional[str]:
        if not self.client:
            item = self.local_cache.get(key)
            if item and item['expiry'] > time.time():
                return item['value']
            return None
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        if not self.client:
            self.local_cache[key] = {
                'value': value,
                'expiry': time.time() + ttl
            }
        else:
            self.client.setex(key, ttl, value)

# =============================================================================
#                            Market Processing Core
# =============================================================================

class MarketEngine:
    """Processes concurrent real-time metrics pipelines without yfinance."""
    def __init__(self, db_mgr: DatabaseManager, cache_mgr: RedisCacheManager):
        self.db = db_mgr
        self.cache = cache_mgr
        self.executor = ThreadPoolExecutor(max_workers=Config.MAX_CONCURRENT_WORKERS)
        self.openai_client = OpenAI(api_key=Config.OPENAI_API_KEY) if Config.OPENAI_API_KEY else None

    def fetch_ticker_data(self, ticker: str) -> Optional[FinancialMetric]:
        normalized_ticker = ticker.upper().strip()
        cache_key = f"metric:{normalized_ticker}"
        
        cached_data = self.cache.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            return FinancialMetric(**data)

        try:
            url = f"https://alphavantage.co{normalized_ticker}&apikey={Config.ALPHA_VANTAGE_API_KEY}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json() or {}
            
            quote = data.get("Global Quote", {})
            if not quote or "05. price" not in quote:
                fallback = self.db.get_metric(normalized_ticker)
                if fallback:
                    return FinancialMetric(**fallback)
                return None

            metric = FinancialMetric(
                ticker=normalized_ticker,
                price=float(quote.get("05. price", 0.0)),
                pe_ratio=None, 
                market_cap=0.0,
                volume=int(quote.get("06. volume", 0))
            )

            self.cache.set(cache_key, metric.to_json(), Config.CACHE_TTL)
            self.executor.submit(self.db.save_metric, metric)
            return metric

        except Exception as e:
            logger.error("market_fetch_failed", ticker=normalized_ticker, error=str(e))
            fallback = self.db.get_metric(normalized_ticker)
            return FinancialMetric(**fallback) if fallback else None

    def analyze_sentiment(self, ticker: str, metrics: FinancialMetric) -> MarketTrend:
        if not self.openai_client:
            return MarketTrend.NEUTRAL

        try:
            prompt = f"Analyze market structural health for {ticker}. Data: {metrics.to_json()}. Output strictly one word: BULLISH, BEARISH, or NEUTRAL."
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0.0
            )
            verdict = response.choices[0].message.content.strip().upper()
            return MarketTrend(verdict)
        except Exception as e:
            logger.error("sentiment_analysis_failed", ticker=ticker, error=str(e))
            return MarketTrend.NEUTRAL

# =============================================================================
#                          Security Primitives & Decorators
# =============================================================================

def signature_required(secret_key: str):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get('X-Hub-Signature-256')
            if not signature:
                return jsonify({"error": "Missing security signature payload header context"}), 401
            
            payload = request.get_data()
            computed_sig = "sha256=" + hmac.new(
                secret_key.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(computed_sig, signature):
                logger.warn("cryptographic_handshake_rejected", remote_ip=request.remote_addr)
                return jsonify({"error": "Invalid cryptographic verification token identity"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

