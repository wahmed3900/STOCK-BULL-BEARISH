import os
import re
import json
import asyncio
import logging
import time
import requests
import pandas as pd
from functools import wraps
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, g
import yfinance as yf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import structlog
from flask_swagger_ui import get_swaggerui_blueprint
from flask_wtf.csrf import CSRFProtect
import redis
from redis import Redis

# Load environment variables
load_dotenv()

# Configure structlog for structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# ==================== Configuration ====================

class Config:
    """Base application configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required")

    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'

    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', "200 per day;50 per hour")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', "memory://")

    CACHE_MAXSIZE = int(os.environ.get('CACHE_MAXSIZE', 1000))
    CACHE_TTL = int(os.environ.get('CACHE_TTL', 3600))

    API_VERSION = "1.0.0"
    MAX_SYMBOL_LENGTH = 10
    MIN_QUERY_LENGTH = 2
    MAX_BATCH_SIZE = 20
    REQUEST_TIMEOUT = 10

    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'app.log')

    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')

    REDIS_URL = os.environ.get('REDIS_URL')
    REDIS_POOL_SIZE = int(os.environ.get('REDIS_POOL_SIZE', 10))
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 4))

    @classmethod
    def validate(cls):
        if cls.REDIS_URL and not cls.REDIS_URL.startswith(('redis://', 'rediss://', 'memory://')):
            raise ValueError("Invalid REDIS_URL format. Must start with redis://, rediss://, or memory://")

class DevelopmentConfig(Config):
    DEBUG = True
    RATELIMIT_DEFAULT = "100 per minute"
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    DEBUG = False
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    TESTING = True
    RATELIMIT_DEFAULT = "1000 per minute"
    SESSION_COOKIE_SECURE = False

# ==================== Enums ====================

class UserTier(Enum):
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

class MarketPeriod(Enum):
    DAY = "1d"
    WEEK = "5d"
    MONTH = "1mo"
    THREE_MONTH = "3mo"
    SIX_MONTH = "6mo"
    YEAR = "1y"
    TWO_YEAR = "2y"
    FIVE_YEAR = "5y"
    MAX = "max"

class CacheStatus(Enum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"

# ==================== Data Classes ====================

@dataclass
class TickerInfo:
    symbol: str
    valid: bool
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None
    country: Optional[str] = None
    exchange: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
    cache_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

@dataclass
class HealthCheck:
    status: str
    timestamp: str
    services: Dict[str, str]
    version: str
    details: Optional[Dict[str, Any]] = None

# ==================== Cache Implementation ====================

class RedisCache:
    def __init__(self, redis_url: Optional[str] = None, ttl: int = 3600, maxsize: int = 1000):
        self.ttl = ttl
        self.maxsize = maxsize
        self.redis_url = redis_url or "memory://"
        self._client = None
        self._memory_cache = {}
        self._setup_client()

    def _setup_client(self):
        if self.redis_url.startswith(('redis://', 'rediss://')):
            try:
                pool = redis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=Config.REDIS_POOL_SIZE,
                    decode_responses=True
                )
                self._client = Redis(connection_pool=pool)
                self._client.ping()
                logger.info("redis_connected", url=self.redis_url)
            except Exception as e:
                logger.error("redis_connection_failed", error=str(e))
                self._client = None
                self._use_memory_fallback()
        else:
            self._use_memory_fallback()

    def _use_memory_fallback(self):
        self._client = None
        logger.info("cache_fallback_memory")

    def get(self, key: str) -> Tuple[Optional[Dict[str, Any]], CacheStatus]:
        if self._client:
            try:
                value = self._client.get(key)
                if value:
                    return json.loads(value), CacheStatus.HIT
                return None, CacheStatus.MISS
            except Exception as e:
                logger.error("redis_get_failed", key=key, error=str(e))
                return None, CacheStatus.MISS

        if key in self._memory_cache:
            value, timestamp = self._memory_cache[key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self.ttl):
                return value, CacheStatus.HIT
            del self._memory_cache[key]
            return None, CacheStatus.STALE
        return None, CacheStatus.MISS

    def set(self, key: str, value: Dict[str, Any]) -> bool:
        try:
            serialized = json.dumps(value)
            if self._client:
                self._client.setex(key, self.ttl, serialized)
                return True

            if len(self._memory_cache) >= self.maxsize:
                oldest = min(self._memory_cache.keys(), key=lambda k: self._memory_cache[k][1])
                del self._memory_cache[oldest]
            self._memory_cache[key] = (value, datetime.now(timezone.utc))
            return True
        except Exception as e:
            logger.error("cache_set_failed", key=key, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        try:
            if self._client:
                self._client.delete(key)
            if key in self._memory_cache:
                del self._memory_cache[key]
            return True
        except Exception as e:
            logger.error("cache_delete_failed", key=key, error=str(e))
            return False

    def clear(self) -> bool:
        try:
            if self._client:
                self._client.flushdb()
            self._memory_cache.clear()
            return True
        except Exception as e:
            logger.error("cache_clear_failed", error=str(e))
            return False

# ==================== Initialize Flask App ====================

env = os.environ.get('FLASK_ENV', 'production')
if env == 'development':
    app_config = DevelopmentConfig
elif env == 'testing':
    app_config = TestingConfig
else:
    app_config = ProductionConfig

app_config.validate()

app = Flask(__name__)
app.config.from_object(app_config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

CORS(app, resources={
    r"/api/*": {
        "origins": app_config.CORS_ORIGINS,
        "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization", "X-CSRFToken"],
        "expose_headers": ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
    }
})

csrf = CSRFProtect(app)

def setup_logging():
    log_level = getattr(logging, app_config.LOG_LEVEL.upper())
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    file_handler = logging.FileHandler(app_config.LOG_FILE)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))
    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(log_level)

setup_logging()

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[app_config.RATELIMIT_DEFAULT],
    strategy=app_config.RATELIMIT_STRATEGY,
    storage_uri=app_config.RATELIMIT_STORAGE_URI
)

cache = RedisCache(
    redis_url=app_config.REDIS_URL,
    ttl=app_config.CACHE_TTL,
    maxsize=app_config.CACHE_MAXSIZE
)

executor = ThreadPoolExecutor(max_workers=app_config.MAX_WORKERS)

# ==================== Swagger/OpenAPI ====================

SWAGGER_URL = '/api/docs'

@app.route('/static/swagger.json')
def swagger_spec():
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Stock Validator API",
            "version": Config.API_VERSION,
            "description": "Stock ticker validation and market data API",
        },
        "paths": {
            "/api/model": {"get": {"summary": "Get model information"}},
            "/api/validate-ticker": {
                "get": {
                    "summary": "Validate a ticker symbol",
                    "parameters": [{"name": "symbol", "in": "query", "required": True, "schema": {"type": "string"}}]
                }
            },
            "/api/batch-validate": {
                "post": {
                    "summary": "Batch validate tickers",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"symbols": {"type": "array", "items": {"type": "string"}}}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return jsonify(spec)

try:
    swaggerui_blueprint = get_swaggerui_blueprint(
        SWAGGER_URL,
        '/static/swagger.json',
        config={'app_name': "Stock Validator API"}
    )
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
except Exception as e:
    logger.warning("swagger_ui_failed", error=str(e))

# ==================== Utilities ====================

def validate_symbol_format(symbol: str) -> bool:
    return bool(re.match(r'^[A-Z]{1,10}$', symbol))

def validate_interval(interval: str) -> bool:
    valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
    return interval in valid_intervals

def safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None

def safe_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None

# ==================== Ticker Validation ====================

def validate_ticker_sync(symbol: str) -> TickerInfo:
    if not validate_symbol_format(symbol):
        return TickerInfo(symbol=symbol, valid=False, error="Invalid format - use 1-10 uppercase letters")

    cache_key = f"ticker_{symbol}"
    cached_value, cache_status = cache.get(cache_key)
    if cached_value:
        result = TickerInfo(**cached_value)
        result.cached = True
        result.cache_status = cache_status.value
        return result

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if info and info.get('symbol'):
            result = TickerInfo(
                symbol=info.get('symbol'),
                valid=True,
                name=info.get('longName') or info.get('shortName') or symbol,
                sector=info.get('sector'),
                industry=info.get('industry'),
                market=info.get('market'),
                currency=info.get('currency'),
                country=info.get('country'),
                exchange=info.get('exchange'),
                cached=False
            )
            cache.set(cache_key, result.to_dict())
            return result
        return TickerInfo(symbol=symbol, valid=False, error="Ticker not found")
    except requests.exceptions.Timeout:
        logger.error("validation_timeout", symbol=symbol)
        return TickerInfo(symbol=symbol, valid=False, error="Request timeout")
    except requests.exceptions.ConnectionError:
        logger.error("validation_connection_error", symbol=symbol)
        return TickerInfo(symbol=symbol, valid=False, error="Connection error")
    except Exception as e:
        logger.error("validation_error", symbol=symbol, error=str(e))
        return TickerInfo(symbol=symbol, valid=False, error=str(e))

# ==================== Decorators ====================

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated

def require_premium(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        tier = session.get('tier', 'free')
        if tier not in ['premium', 'enterprise']:
            return jsonify({'error': 'Premium feature - upgrade required'}), 403
        return f(*args, **kwargs)
    return decorated

def log_request(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        start = time.time()
        response = f(*args, **kwargs)
        duration = time.time() - start
        logger.info(
            "api_request",
            endpoint=request.path,
            method=request.method,
            status_code=response[1] if isinstance(response, tuple) else response.status_code,
            duration_ms=round(duration * 1000, 2),
            ip=request.remote_addr
        )
        return response
    return decorated

# ==================== API Routes ====================

@app.route('/api/model', methods=['HEAD', 'GET'])
@log_request
def get_model():
    """Get model information (required by UptimeRobot)"""
    return jsonify({
        "status": "active",
        "model": "stock_validator",
        "version": Config.API_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "features": {
            "ticker_validation": True,
            "market_data": session.get('tier', 'free') in ['premium', 'enterprise'],
            "batch_validation": True,
            "historical_data": session.get('tier', 'free') in ['premium', 'enterprise'],
            "async_validation": True
        },
        "rate_limits": {
            "default": Config.RATELIMIT_DEFAULT,
            "validate_ticker": "10 per minute",
            "batch_validate": "2 per minute",
            "market_data": "30 per minute"
        }
    }), 200

@app.route('/api/validate-ticker', methods=['GET'])
@limiter.limit("10 per minute")
@log_request
def validate_ticker():
    symbol = request.args.get('symbol', '').strip().upper()
    if not symbol:
        return jsonify({'valid': False, 'error': 'No symbol provided'}), 400
    result = validate_ticker_sync(symbol)
    response = result.to_dict()
    response['cached'] = result.cached
    return jsonify(response), 200 if result.valid else 404

@app.route('/api/batch-validate', methods=['POST'])
@limiter.limit("2 per minute")
@log_request
def batch_validate():
    data = request.get_json()
    if not data or 'symbols' not in data:
        return jsonify({'error': 'Missing symbols array'}), 400
    symbols = data.get('symbols', [])
    if not isinstance(symbols, list):
        return jsonify({'error': 'Symbols must be an array'}), 400
    if len(symbols) > Config.MAX_BATCH_SIZE:
        return jsonify({'error': f'Maximum {Config.MAX_BATCH_SIZE} symbols per batch'}), 400

    with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
        results = list(executor.map(validate_ticker_sync, symbols))
    return jsonify({
        'results': [r.to_dict() for r in results],
        'total': len(results),
        'valid_count': sum(1 for r in results if r.valid),
        'cached_count': sum(1 for r in results if r.cached),
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    }), 200

@app.route('/api/search-tickers', methods=['GET'])
@limiter.limit("10 per minute")
@log_request
def search_tickers():
    query = request.args.get('q', '').strip().upper()
    if len(query) < Config.MIN_QUERY_LENGTH:
        return jsonify({'suggestions': [], 'message': f'Minimum query length is {Config.MIN_QUERY_LENGTH}'}), 200

    cache_key = f"search_{query}"
    cached_value, _ = cache.get(cache_key)
    if cached_value:
        return jsonify({'suggestions': cached_value, 'cached': True, 'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'}), 200

    try:
        ticker = yf.Ticker(query)
        info = ticker.info
        if info and info.get('symbol'):
            suggestion = [{
                'symbol': info.get('symbol'),
                'name': info.get('longName') or info.get('shortName') or query,
                'type': info.get('quoteType', 'Unknown'),
                'exchange': info.get('exchange', 'Unknown'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'market': info.get('market', 'Unknown')
            }]
            cache.set(cache_key, suggestion)
            return jsonify({'suggestions': suggestion, 'cached': False, 'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'}), 200
    except Exception as e:
        logger.error("search_error", query=query, error=str(e))

    return jsonify({'suggestions': [], 'cached': False, 'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'}), 200

@app.route('/api/market-data', methods=['GET'])
@limiter.limit("30 per minute")
@require_auth
@require_premium
@log_request
def get_market_data():
    symbol = request.args.get('symbol', '').strip().upper()
    period = request.args.get('period', '1mo')
    interval = request.args.get('interval', '1d')

    if not symbol or not validate_symbol_format(symbol):
        return jsonify({'error': 'Invalid symbol'}), 400

    try:
        MarketPeriod(period)
    except ValueError:
        return jsonify({'error': f'Invalid period. Options: {[p.value for p in MarketPeriod]}'}), 400

    if not validate_interval(interval):
        return jsonify({'error': f'Invalid interval'}), 400

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or not info.get('symbol'):
            return jsonify({'error': 'Ticker not found'}), 404

        cache_key = f"market_data_{symbol}_{period}_{interval}"
        cached_value, _ = cache.get(cache_key)
        if cached_value:
            return jsonify(cached_value), 200

        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return jsonify({'error': 'No data found'}), 404

        # Build response (simplified)
        data = {
            'symbol': symbol,
            'period': period,
            'interval': interval,
            'data': hist.reset_index().to_dict('records'),
            'summary': {
                'name': info.get('longName') or info.get('shortName') or symbol,
                'sector': info.get('sector'),
                'exchange': info.get('exchange'),
                'currency': info.get('currency', 'USD'),
                'current_price': float(hist['Close'].iloc[-1]) if 'Close' in hist.columns and len(hist) > 0 else None,
            },
            'metadata': {'fetched_at': datetime.now(timezone.utc).isoformat() + 'Z', 'cached': False}
        }
        # Convert timestamps
        for record in data['data']:
            for key, value in list(record.items()):
                if isinstance(value, (datetime, pd.Timestamp)):
                    record[key] = value.isoformat()
        cache.set(cache_key, data)
        return jsonify(data), 200
    except Exception as e:
        logger.error("market_data_error", symbol=symbol, error=str(e))
        return jsonify({'error': 'Failed to fetch market data'}), 500

@app.route('/api/ticker-info', methods=['GET'])
@limiter.limit("30 per minute")
@log_request
def get_ticker_info():
    symbol = request.args.get('symbol', '').strip().upper()
    if not symbol or not validate_symbol_format(symbol):
        return jsonify({'error': 'Invalid symbol'}), 400

    result = validate_ticker_sync(symbol)
    if not result.valid:
        return jsonify({'error': 'Ticker not found'}), 404

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        current_price = None
        try:
            hist = ticker.history(period='1d')
            if not hist.empty and 'Close' in hist.columns:
                current_price = float(hist['Close'].iloc[-1])
        except:
            pass

        response = result.to_dict()
        response.update({
            'current_price': current_price,
            'market_cap': safe_float(info.get('marketCap')),
            'pe_ratio': safe_float(info.get('trailingPE')),
            'dividend_yield': safe_float(info.get('dividendYield')),
            'beta': safe_float(info.get('beta')),
            'recommendation': info.get('recommendationKey', 'Unknown')
        })
        return jsonify(response), 200
    except Exception as e:
        logger.error("ticker_info_error", symbol=symbol, error=str(e))
        return jsonify(result.to_dict()), 200

@app.route('/api/cache/clear', methods=['POST'])
@require_auth
@require_premium
@log_request
def clear_cache():
    try:
        cache.clear()
        return jsonify({'message': 'Cache cleared', 'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'}), 200
    except Exception as e:
        logger.error("cache_clear_error", error=str(e))
        return jsonify({'error': 'Failed to clear cache'}), 500

@app.route('/api/health', methods=['GET'])
@log_request
def health_check():
    services = {}
    healthy = True
    try:
        test = yf.Ticker("AAPL")
        if test.info and test.info.get('symbol'):
            services['yfinance'] = 'healthy'
        else:
            services['yfinance'] = 'degraded'
            healthy = False
    except:
        services['yfinance'] = 'unhealthy'
        healthy = False
    services['cache'] = 'healthy'  # simplified
    services['ratelimiter'] = 'healthy'
    return jsonify({
        'status': 'healthy' if healthy else 'degraded',
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
        'services': services,
        'version': Config.API_VERSION,
        'details': {'environment': env}
    }), 200 if healthy else 503

# ==================== Web Routes ====================

@app.route('/')
def dashboard():
    tier = session.get('tier', UserTier.FREE.value)
    return render_template('base.html',
                         tier=tier,
                         user_name=session.get('user_name', 'Guest'),
                         user_id=session.get('user_id'),
                         year=datetime.now(timezone.utc).year,
                         features={
                             'premium': tier in ['premium', 'enterprise'],
                             'can_search': True,
                             'can_validate': True,
                             'can_batch': True,
                             'can_cache_clear': tier in ['premium', 'enterprise']
                         },
                         version=Config.API_VERSION)

@app.route('/demo_login')
def demo_login():
    session.clear()
    session.permanent = True
    session['user_id'] = 'demo_user'
    session['user_name'] = 'Demo User'
    session['tier'] = 'premium'
    session['login_time'] = datetime.now(timezone.utc).isoformat()  # Fixed missing assignment
    logger.info("demo_login", user_id='demo_user', tier='premium')
    flash('Logged in as Demo User (Premium Tier)', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('dashboard'))

# ==================== Debug Route (optional) ====================

@app.route('/debug/routes')
def debug_routes():
    routes = sorted([str(rule) for rule in app.url_map.iter_rules()])
    return "<br>".join(routes)

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded', 'retry_after': 60}), 429

@app.errorhandler(500)
def server_error(e):
    logger.error("server_error", error=str(e))
    return jsonify({'error': 'Internal server error'}), 500

# ==================== Main Entry Point ====================

if __name__ == '__main__':
    app.config['START_TIME'] = time.time()
    port = int(os.environ.get('PORT', 5000))
    debug = app_config.DEBUG
    if debug:
        app.run(debug=True, host='0.0.0.0', port=port)
    else:
        try:
            from gevent.pywsgi import WSGIServer
            logger.info("starting_gevent_server", port=port, environment=env)
            http_server = WSGIServer(('0.0.0.0', port), app)
            http_server.serve_forever()
        except ImportError:
            app.run(debug=False, host='0.0.0.0', port=port)# Redeploy trigger
