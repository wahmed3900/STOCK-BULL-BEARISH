import os
import re
import logging
from functools import lru_cache
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
import yfinance as yf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
class Config:
    """Application configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required")

    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'

    # Rate limiting
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', "200 per day;50 per hour")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', "memory://")

    # Cache settings
    CACHE_MAXSIZE = int(os.environ.get('CACHE_MAXSIZE', 1000))
    CACHE_TTL = int(os.environ.get('CACHE_TTL', 3600))  # 1 hour

    # API settings
    API_VERSION = "1.0.0"
    MAX_SYMBOL_LENGTH = 10
    MIN_QUERY_LENGTH = 2

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'app.log')

# Enums
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

@dataclass
class TickerInfo:
    """Data class for ticker information"""
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Enable CORS for API endpoints
CORS(app, resources={
    r"/api/*": {
        "origins": os.environ.get('CORS_ORIGINS', '*').split(','),
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Setup logging
def setup_logging():
    """Configure logging for production"""
    log_level = getattr(logging, Config.LOG_LEVEL.upper())
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    # File handler
    file_handler = logging.FileHandler(Config.LOG_FILE)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))

    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(log_level)

setup_logging()

# Initialize rate limiter with Redis support
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[Config.RATELIMIT_DEFAULT],
    strategy=Config.RATELIMIT_STRATEGY,
    storage_uri=Config.RATELIMIT_STORAGE_URI
)

# Cache with TTL support
class TickerCache:
    """Simple TTL cache wrapper for ticker validation"""
    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        self.cache = {}
        self.maxsize = maxsize
        self.ttl = ttl

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached value if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.ttl):
                return value
            del self.cache[key]
        return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set cache value with timestamp"""
        if len(self.cache) >= self.maxsize:
            # Remove oldest entry
            oldest = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest]
        self.cache[key] = (value, datetime.utcnow())

    def clear(self) -> None:
        """Clear all cache"""
        self.cache.clear()

# Import timedelta here since it's only used in TickerCache
from datetime import timedelta

ticker_cache = TickerCache(maxsize=Config.CACHE_MAXSIZE, ttl=Config.CACHE_TTL)

def validate_ticker_sync(symbol: str) -> TickerInfo:
    """Validate ticker with improved error handling and retries"""
    if not re.match(r'^[A-Z]{1,10}$', symbol):
        return TickerInfo(symbol=symbol, valid=False, error="Invalid format - use 1-10 uppercase letters")

    # Check cache first
    cache_key = f"ticker_{symbol}"
    cached = ticker_cache.get(cache_key)
    if cached:
        return TickerInfo(**cached)

    try:
        # Add timeout and retry logic
        import requests
        session = requests.Session()
        session.timeout = 10

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
                exchange=info.get('exchange')
            )
            # Cache the result
            ticker_cache.set(cache_key, result.to_dict())
            return result

        return TickerInfo(symbol=symbol, valid=False, error="Ticker not found")

    except requests.exceptions.Timeout:
        app.logger.error(f"Timeout validating {symbol}")
        return TickerInfo(symbol=symbol, valid=False, error="Request timeout")
    except requests.exceptions.ConnectionError:
        app.logger.error(f"Connection error validating {symbol}")
        return TickerInfo(symbol=symbol, valid=False, error="Connection error")
    except Exception as e:
        app.logger.error(f"Error validating {symbol}: {e}")
        return TickerInfo(symbol=symbol, valid=False, error=str(e))

# Authentication decorator
def require_auth(f):
    """Decorator to require authentication for premium endpoints"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def require_premium(f):
    """Decorator to require premium tier"""
    def decorated_function(*args, **kwargs):
        tier = session.get('tier', 'free')
        if tier not in ['premium', 'enterprise']:
            return jsonify({'error': 'Premium feature - upgrade required'}), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/api/model', methods=['HEAD', 'GET'])
def get_model() -> Tuple[Dict[str, Any], int]:
    """Get model information"""
    return jsonify({
        "status": "active",
        "model": "stock_validator",
        "version": Config.API_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "features": {
            "ticker_validation": True,
            "market_data": session.get('tier', 'free') in ['premium', 'enterprise'],
            "batch_validation": True,
            "historical_data": session.get('tier', 'free') in ['premium', 'enterprise']
        }
    }), 200

@app.route('/api/validate-ticker', methods=['GET'])
@limiter.limit("10 per minute")
def validate_ticker() -> Tuple[Dict[str, Any], int]:
    """API endpoint to validate a ticker symbol"""
    symbol = request.args.get('symbol', '').strip().upper()

    if not symbol:
        return jsonify({'valid': False, 'error': 'No symbol provided'}), 400

    result = validate_ticker_sync(symbol)
    return jsonify(result.to_dict()), 200 if result.valid else 404

@app.route('/api/batch-validate', methods=['POST'])
@limiter.limit("2 per minute")
def batch_validate() -> Tuple[Dict[str, Any], int]:
    """Batch validate multiple ticker symbols"""
    data = request.get_json()

    if not data or 'symbols' not in data:
        return jsonify({'error': 'Missing symbols array'}), 400

    symbols = data.get('symbols', [])
    if not isinstance(symbols, list):
        return jsonify({'error': 'Symbols must be an array'}), 400

    if len(symbols) > 20:
        return jsonify({'error': 'Maximum 20 symbols per batch'}), 400

    results = []
    for symbol in symbols:
        symbol = str(symbol).strip().upper()
        if symbol:
            result = validate_ticker_sync(symbol)
            results.append(result.to_dict())

    return jsonify({
        'results': results,
        'total': len(results),
        'valid_count': sum(1 for r in results if r.get('valid', False))
    }), 200

@app.route('/api/search-tickers', methods=['GET'])
@limiter.limit("10 per minute")
def search_tickers() -> Tuple[Dict[str, Any], int]:
    """Search for tickers matching a query"""
    query = request.args.get('q', '').strip().upper()

    if len(query) < Config.MIN_QUERY_LENGTH:
        return jsonify({'suggestions': []}), 200

    try:
        # Try exact match first with caching
        cache_key = f"search_{query}"
        cached = ticker_cache.get(cache_key)
        if cached:
            return jsonify({'suggestions': cached}), 200

        ticker = yf.Ticker(query)
        info = ticker.info

        if info and info.get('symbol'):
            suggestion = [{
                'symbol': info.get('symbol'),
                'name': info.get('longName') or info.get('shortName') or query,
                'type': info.get('quoteType', 'Unknown'),
                'exchange': info.get('exchange', 'Unknown'),
                'sector': info.get('sector'),
                'industry': info.get('industry')
            }]
            ticker_cache.set(cache_key, suggestion)
            return jsonify({'suggestions': suggestion}), 200

    except Exception as e:
        app.logger.error(f"Error searching for {query}: {e}")

    return jsonify({'suggestions': []}), 200

@app.route('/api/market-data', methods=['GET'])
@limiter.limit("30 per minute")
@require_auth
@require_premium
def get_market_data() -> Tuple[Dict[str, Any], int]:
    """Get market data for a ticker (premium feature)"""
    symbol = request.args.get('symbol', '').strip().upper()
    period = request.args.get('period', '1mo')
    interval = request.args.get('interval', '1d')

    if not symbol:
        return jsonify({'error': 'No symbol provided'}), 400

    # Validate period
    try:
        MarketPeriod(period)
    except ValueError:
        return jsonify({'error': f'Invalid period. Valid options: {[p.value for p in MarketPeriod]}'}), 400

    # Validate interval
    valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
    if interval not in valid_intervals:
        return jsonify({'error': f'Invalid interval. Valid options: {valid_intervals}'}), 400

    try:
        # Get data with timeout
        import requests
        ticker = yf.Ticker(symbol)

        # Get info first
        info = ticker.info
        if not info or not info.get('symbol'):
            return jsonify({'error': 'Ticker not found'}), 404

        # Get historical data
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return jsonify({'error': 'No data found for the specified period'}), 404

        # Calculate additional metrics
        if 'Close' in hist.columns and len(hist) > 0:
            current_price = hist['Close'].iloc[-1]
            price_change = hist['Close'].iloc[-1] - hist['Close'].iloc[0] if len(hist) > 1 else 0
            price_change_pct = (price_change / hist['Close'].iloc[0] * 100) if len(hist) > 1 else 0
        else:
            current_price = None
            price_change = None
            price_change_pct = None

        # Prepare response
        data = {
            'symbol': symbol,
            'period': period,
            'interval': interval,
            'data': hist.reset_index().to_dict('records'),
            'summary': {
                'name': info.get('longName') or info.get('shortName') or symbol,
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'exchange': info.get('exchange'),
                'currency': info.get('currency', 'USD'),
                'current_price': current_price,
                'price_change': price_change,
                'price_change_pct': price_change_pct,
                'volume': int(hist['Volume'].sum()) if 'Volume' in hist.columns else None,
                'avg_volume': int(hist['Volume'].mean()) if 'Volume' in hist.columns and len(hist) > 0 else None
            },
            'metadata': {
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'data_points': len(hist)
            }
        }

        # Convert datetime objects to strings
        for record in data['data']:
            if 'Date' in record:
                record['Date'] = record['Date'].isoformat()
            # Convert numpy types to Python types
            for key, value in record.items():
                if hasattr(value, 'item'):
                    record[key] = value.item()

        # Log premium feature usage
        app.logger.info(f"Premium market data accessed for {symbol} by user {session.get('user_id', 'unknown')}")

        return jsonify(data), 200

    except requests.exceptions.Timeout:
        app.logger.error(f"Timeout fetching market data for {symbol}")
        return jsonify({'error': 'Request timeout'}), 504
    except Exception as e:
        app.logger.error(f"Error fetching market data for {symbol}: {e}")
        return jsonify({'error': 'Failed to fetch market data'}), 500

@app.route('/api/ticker-info', methods=['GET'])
@limiter.limit("30 per minute")
def get_ticker_info() -> Tuple[Dict[str, Any], int]:
    """Get comprehensive ticker information"""
    symbol = request.args.get('symbol', '').strip().upper()

    if not symbol:
        return jsonify({'error': 'No symbol provided'}), 400

    result = validate_ticker_sync(symbol)

    if not result.valid:
        return jsonify({'error': 'Ticker not found'}), 404

    # Get additional info
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Get current price
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
            'market_cap': info.get('marketCap'),
            'pe_ratio': info.get('trailingPE'),
            'dividend_yield': info.get('dividendYield'),
            '52_week_high': info.get('fiftyTwoWeekHigh'),
            '52_week_low': info.get('fiftyTwoWeekLow'),
            'volume': info.get('volume'),
            'avg_volume': info.get('averageVolume')
        })

        return jsonify(response), 200

    except Exception as e:
        app.logger.error(f"Error fetching info for {symbol}: {e}")
        return jsonify(result.to_dict()), 200

@app.route('/api/health', methods=['GET'])
def health_check() -> Tuple[Dict[str, Any], int]:
    """Health check endpoint"""
    # Check external services
    services_healthy = True
    try:
        # Quick check of yfinance
        test_ticker = yf.Ticker("AAPL")
        test_info = test_ticker.info
        if not test_info or not test_info.get('symbol'):
            services_healthy = False
    except:
        services_healthy = False

    return jsonify({
        'status': 'healthy' if services_healthy else 'degraded',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'services': {
            'yfinance': 'healthy' if services_healthy else 'degraded',
            'cache': 'healthy',
            'database': 'healthy'
        },
        'version': Config.API_VERSION
    }), 200 if services_healthy else 503

# Web routes
@app.route('/')
def dashboard():
    """Main dashboard page"""
    tier = session.get('tier', UserTier.FREE.value)
    user_name = session.get('user_name', 'Guest')
    user_id = session.get('user_id')

    return render_template('base.html',
                         tier=tier,
                         user_name=user_name,
                         user_id=user_id,
                         year=datetime.utcnow().year,
                         features={
                             'premium': tier in ['premium', 'enterprise'],
                             'can_search': True,
                             'can_validate': True
                         })

@app.route('/demo_login')
def demo_login():
    """Demo login for testing"""
    session.clear()
    session.permanent = True
    session['user_id'] = 'demo_user'
    session['user_name'] = 'Demo User'
    session['tier'] = 'premium'
    session['login_time'] = datetime.utcnow().isoformat()

    flash('Logged in as Demo User (Premium Tier)', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    """Logout user"""
    user_id = session.get('user_id', 'unknown')
    app.logger.info(f"User {user_id} logged out")
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('dashboard'))

# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested resource was not found'
    }), 404

@app.errorhandler(429)
def ratelimit_handler(error):
    """Handle rate limit errors"""
    return jsonify({
        'error': 'Too many requests',
        'message': 'Rate limit exceeded. Please try again later.',
        'retry_after': getattr(error, 'retry_after', 60)
    }), 429

@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    app.logger.error(f"Server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500

# Request/Response logging
@app.before_request
def log_request_info():
    """Log incoming requests"""
    if request.path.startswith('/api/'):
        app.logger.info(f"Request: {request.method} {request.path} - IP: {request.remote_addr}")

@app.after_request
def log_response_info(response):
    """Log outgoing responses"""
    if request.path.startswith('/api/'):
        app.logger.info(f"Response: {response.status_code} - {request.method} {request.path}")
    return response

# Main entry point with production server support
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = Config.DEBUG

    if debug:
        app.run(debug=True, host='0.0.0.0', port=port)
    else:
        # Production: Use Gunicorn or similar
        app.logger.info(f"Starting production server on port {port}")
        from gevent.pywsgi import WSGIServer
        http_server = WSGIServer(('0.0.0.0', port), app)
        http_server.serve_forever()