# =============================================================================
#                         Stock Analysis Flask Application
# =============================================================================

import sys
import io
import os
import time
import logging
import sqlite3
import hashlib
import requests
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, render_template

from src.secret_manager import get_api_key, get_secret

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment variables
load_dotenv()

# =============================================================================
#                               CONFIGURATION
# =============================================================================

def resolve_secret(env_name: str, secret_name: str | None = None):
    """Return an environment variable, or fall back to Google Secret Manager."""
    secret_value = os.environ.get(env_name)
    if secret_value:
        return secret_value

    if secret_name:
        if secret_name in {"alpha_vantage", "polygon", "finnhub", "docker"}:
            try:
                return get_api_key(secret_name)
            except Exception:
                return None
        try:
            return get_secret(secret_name)
        except Exception:
            return None

    return None


class Config:
    """Application configuration"""
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    ENV = os.environ.get('FLASK_ENV', 'development')
    PORT = int(os.environ.get('PORT', 5000))
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # OpenRouter API Configuration
    OPENROUTER_API_KEY = resolve_secret("OPENROUTER_API_KEY", "openrouter-api-key")
    ALPHA_VANTAGE_API_KEY = resolve_secret("ALPHA_VANTAGE_API_KEY", "alpha-vantage-key")
    
    # Fallback model list
    PREFERRED_MODELS = [
        "nvidia/nv-remote-3-ultra",
        "ling/ling-3.0-flash",
        "cohere/north-mini-code",
        "google/gemini-flash-1.5",
    ]

# =============================================================================
#                               INITIALIZE FLASK APP
# =============================================================================

app = Flask(__name__, template_folder="templates")
app.config.from_object(Config)
app.secret_key = app.config.get("SECRET_KEY", "dev-secret-key-change-in-production")

# =============================================================================
#                               LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

FREE_TIER_LIMIT = 3


def get_db():
    """Return a SQLite connection for local user and plan persistence."""
    db_path = app.config.get("DATABASE_PATH")
    if not db_path:
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "subscriptions.sqlite3")
        app.config["DATABASE_PATH"] = db_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the local database tables needed for auth and subscriptions."""
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            stripe_customer_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    row = conn.execute(
        "SELECT id, username, plan, stripe_customer_id FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def is_pro_user(user):
    return bool(user and user.get("plan") == "pro")


# =============================================================================
#                         STOCK ANALYSIS FUNCTIONS
# =============================================================================

def get_stock_data(ticker):
    """Fetch current price and basic info for a stock."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None, "Price data not available"
        return {
            "price": price,
            "name": info.get("longName", ticker),
            "currency": info.get("currency", "USD"),
            "previous_close": info.get("previousClose", None),
            "day_high": info.get("dayHigh", None),
            "day_low": info.get("dayLow", None),
            "volume": info.get("volume", None)
        }, None
    except Exception as e:
        return None, f"Failed to fetch stock data: {e}"

def call_ai_model(prompt, model_list=None):
    """
    Call OpenRouter with a fallback list of models.
    """
    if model_list is None:
        model_list = Config.PREFERRED_MODELS
    
    if not Config.OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY is not set"

    errors = []

    for model in model_list:
        try:
            logger.info(f"Trying model: {model}")
            
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a professional financial analyst. Provide concise, actionable stock analysis."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"], None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                errors.append(f"{model}: {error_msg}")
                logger.warning(error_msg)
                continue

        except requests.exceptions.Timeout:
            error_msg = f"{model}: Request timed out"
            errors.append(error_msg)
            logger.warning(error_msg)
            continue
        except Exception as e:
            error_msg = f"{model}: {str(e)}"
            errors.append(error_msg)
            logger.warning(error_msg)
            continue

    return None, f"All models failed: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Full pipeline: fetch stock data + AI analysis."""
    # 1. Get stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        return None, error

    # 2. Build the AI prompt
    prompt = f"""
    Analyze the following stock:

    Ticker: {ticker}
    Company: {stock_data['name']}
    Current Price: {stock_data['currency']} {stock_data['price']:.2f}
    Previous Close: {stock_data['currency']} {stock_data['previous_close']:.2f}
    Day Range: {stock_data['currency']} {stock_data['day_low']} - {stock_data['day_high']}
    Volume: {stock_data['volume']}

    Please provide:
    1. A brief sentiment assessment (bullish / bearish / neutral)
    2. The key reason for this sentiment
    3. A 1-2 sentence summary for a quick dashboard display

    Keep your response clear and formatted for easy reading.
    """

    # 3. Call AI with fallback
    analysis, error = call_ai_model(prompt)
    if error:
        return None, error

    # 4. Return combined result
    return {
        "ticker": ticker,
        "name": stock_data['name'],
        "price": stock_data['price'],
        "currency": stock_data['currency'],
        "previous_close": stock_data['previous_close'],
        "day_high": stock_data['day_high'],
        "day_low": stock_data['day_low'],
        "volume": stock_data['volume'],
        "analysis": analysis
    }, None

# =============================================================================
#                               FLASK ROUTES
# =============================================================================

@app.route('/')
def home():
    """Serve the SaaS landing page for the stock dashboard."""
    return render_template('landing.html', app_name='BullBear AI', plan='free')


@app.route('/pricing')
def pricing_page():
    """Render the pricing page for the subscription product."""
    return render_template('pricing.html', plan='free')

@app.route('/status')
def status():
    """Status endpoint showing server uptime"""
    uptime = time.time() - app.config.get('START_TIME', time.time())
    return jsonify({
        'status': 'running',
        'uptime_seconds': round(uptime, 2),
        'environment': Config.ENV,
        'debug_mode': Config.DEBUG,
        'port': Config.PORT,
        'openrouter_configured': bool(Config.OPENROUTER_API_KEY)
    })

@app.route('/health')
def health():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time()
    })

@app.route('/analyze/<ticker>')
def analyze_stock_endpoint(ticker):
    """Analyze a stock by ticker symbol (GET)"""
    ticker = ticker.upper()
    result, error = analyze_stock(ticker)
    
    if error:
        return jsonify({
            'error': 'Analysis failed',
            'message': error,
            'ticker': ticker
        }), 400
    
    return jsonify(result)

@app.route('/analyze', methods=['POST'])
def analyze_stock_post():
    """Analyze a stock by ticker symbol (POST)"""
    data = request.get_json()
    
    if not data or 'ticker' not in data:
        return jsonify({
            'error': 'Missing ticker',
            'message': 'Please provide ticker in JSON: {"ticker": "AAPL"}'
        }), 400
    
    ticker = data['ticker'].upper()
    result, error = analyze_stock(ticker)
    
    if error:
        return jsonify({
            'error': 'Analysis failed',
            'message': error,
            'ticker': ticker
        }), 400
    
    return jsonify(result)

@app.route('/analyze/batch', methods=['POST'])
def analyze_batch():
    """Analyze multiple stocks at once."""
    data = request.get_json(silent=True) or {}

    if not data or 'tickers' not in data:
        return jsonify({
            'error': 'Missing tickers',
            'message': 'Please provide tickers in JSON: {"tickers": ["AAPL", "GOOGL"]}'
        }), 400

    user = get_current_user()
    tickers = [ticker.upper() for ticker in data['tickers']]
    if not is_pro_user(user) and len(tickers) > FREE_TIER_LIMIT:
        return jsonify({
            'error': 'plan_limit',
            'message': f'Your free plan allows up to {FREE_TIER_LIMIT} tickers per batch. Upgrade to Pro for unlimited analysis.'
        }), 403

    results = []
    errors = []

    for ticker in tickers:
        result, error = analyze_stock(ticker)
        if error:
            errors.append({'ticker': ticker, 'error': error})
        else:
            results.append(result)

    return jsonify({
        'results': results,
        'errors': errors,
        'total': len(results) + len(errors),
        'successful': len(results),
        'failed': len(errors),
        'plan': user['plan'] if user else 'free'
    })


@app.route('/auth/register', methods=['POST'])
def register_user():
    """Create a local user account and log them in."""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''

    if not username or len(password) < 6:
        return jsonify({
            'error': 'invalid_request',
            'message': 'Provide a username and a password with at least 6 characters.'
        }), 400

    conn = get_db()
    try:
        cursor = conn.execute(
            'INSERT INTO users (username, password_hash, plan) VALUES (?, ?, ?)',
            (username, _hash_password(password), 'free'),
        )
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            'error': 'username_taken',
            'message': 'That username is already registered.'
        }), 409

    conn.close()
    session['user_id'] = user_id
    return jsonify({
        'message': 'Account created successfully.',
        'user': {'id': user_id, 'username': username, 'plan': 'free'}
    }), 201


@app.route('/auth/login', methods=['POST'])
def login_user():
    """Authenticate a user and store their session."""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''

    conn = get_db()
    row = conn.execute(
        'SELECT id, username, plan, password_hash FROM users WHERE username = ?',
        (username,),
    ).fetchone()
    conn.close()

    if not row or row['password_hash'] != _hash_password(password):
        return jsonify({
            'error': 'invalid_credentials',
            'message': 'Incorrect username or password.'
        }), 401

    session['user_id'] = row['id']
    return jsonify({
        'message': 'Logged in successfully.',
        'user': {'id': row['id'], 'username': row['username'], 'plan': row['plan']}
    })


@app.route('/auth/logout', methods=['POST'])
def logout_user():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out successfully.'})


@app.route('/auth/me')
def current_user():
    user = get_current_user()
    if not user:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, 'user': user})


@app.route('/billing/checkout', methods=['POST'])
def create_checkout():
    """Create a Stripe-style checkout session or fall back to a demo upgrade route."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'unauthenticated', 'message': 'Please log in first.'}), 401

    if user['plan'] == 'pro':
        return jsonify({'message': 'You already have a Pro subscription.', 'plan': 'pro'})

    stripe_secret_key = app.config.get('STRIPE_SECRET_KEY')
    stripe_price_id = app.config.get('STRIPE_PRICE_ID')

    if stripe_secret_key and stripe_price_id:
        try:
            import stripe

            stripe.api_key = stripe_secret_key
            session = stripe.checkout.Session.create(
                mode='subscription',
                line_items=[{'price': stripe_price_id, 'quantity': 1}],
                success_url=app.config.get('STRIPE_SUCCESS_URL', 'http://localhost:5000/billing/success'),
                cancel_url=app.config.get('STRIPE_CANCEL_URL', 'http://localhost:5000/billing/cancel'),
                client_reference_id=str(user['id']),
            )
            return jsonify({'checkout_url': session.url, 'plan': 'pro'})
        except Exception as exc:
            logger.warning('Stripe checkout failed: %s', exc)

    return jsonify({
        'message': 'Stripe is not configured yet. Demo mode is active.',
        'plan': 'pro',
        'confirm_url': '/billing/confirm-demo'
    })


@app.route('/billing/confirm-demo', methods=['POST'])
def confirm_demo_checkout():
    """Upgrade the signed-in user to Pro in demo mode."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'unauthenticated', 'message': 'Please log in first.'}), 401

    conn = get_db()
    conn.execute("UPDATE users SET plan = ? WHERE id = ?", ('pro', user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Demo Pro upgrade completed.', 'plan': 'pro'})


# =============================================================================
#                               ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested resource was not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal Server Error: {error}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred'
    }), 500

# =============================================================================
#                               CLI INTERFACE
# =============================================================================

def run_cli():
    """Run as command-line tool"""
    print("\n📊 Stock Analysis Tool (CLI Mode)")
    print("-" * 40)
    
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"
    
    result, error = analyze_stock(ticker)
    
    if error:
        print(f"\n❌ Error: {error}")
        return
    
    print("\n" + "="*50)
    print(f"📈 ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {result['currency']} {result['price']:.2f}")
    print(f"🏷️  Name: {result['name']}")
    print(f"📊 Previous Close: {result['currency']} {result['previous_close']:.2f}")
    print(f"📈 Day Range: {result['currency']} {result['day_low']} - {result['day_high']}")
    print(f"📊 Volume: {result['volume']:,}")
    print("\n🤖 AI Sentiment Analysis:")
    print("-"*50)
    print(result['analysis'])
    print("="*50)

# =============================================================================
#                               MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # Check if running as CLI
    if len(sys.argv) > 1 and sys.argv[1] == 'cli':
        run_cli()
    else:
        # Update config from environment
        Config.DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
        Config.ENV = os.environ.get('FLASK_ENV', 'development')
        Config.PORT = int(os.environ.get('PORT', 5000))
        
        # Track server start time
        app.config['START_TIME'] = time.time()
        init_db()
        
        # Check API key
        if not Config.OPENROUTER_API_KEY:
            logger.warning("⚠️ OPENROUTER_API_KEY not set! AI analysis will fail.")
        
        # Log startup information
        logger.info(f"Starting Flask application in {Config.ENV} mode")
        logger.info(f"Debug mode: {Config.DEBUG}")
        logger.info(f"Port: {Config.PORT}")
        logger.info(f"OpenRouter configured: {bool(Config.OPENROUTER_API_KEY)}")
        
        # Development mode
        if Config.DEBUG:
            logger.info("Running in development mode with Flask built-in server")
            app.run(debug=True, host='0.0.0.0', port=Config.PORT)
        
        # Production mode
        else:
            try:
                from gevent.pywsgi import WSGIServer
                logger.info(f"Starting gevent production server on port {Config.PORT}")
                http_server = WSGIServer(('0.0.0.0', Config.PORT), app)
                logger.info(f"Server running at http://0.0.0.0:{Config.PORT}")
                http_server.serve_forever()
                
            except ImportError:
                logger.warning("gevent not installed - falling back to Flask's built-in server")
                app.run(debug=False, host='0.0.0.0', port=Config.PORT)