# =============================================================================
#                         Stock Analysis Flask Application
# =============================================================================

import sys
import io
import os
import time
import logging
import requests
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask, jsonify, request

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment variables
load_dotenv()

# =============================================================================
#                               CONFIGURATION
# =============================================================================

class Config:
    """Application configuration"""
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    ENV = os.environ.get('FLASK_ENV', 'development')
    PORT = int(os.environ.get('PORT', 5000))
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # OpenRouter API Configuration
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
    
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

app = Flask(__name__)
app.config.from_object(Config)

# =============================================================================
#                               LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    """Home page endpoint"""
    return jsonify({
        'message': 'Stock Analysis API',
        'version': '1.0.0',
        'endpoints': {
            '/status': 'Server status',
            '/health': 'Health check',
            '/analyze/<ticker>': 'Analyze a stock (GET)',
            '/analyze': 'Analyze a stock (POST with JSON)',
            '/analyze/batch': 'Analyze multiple stocks (POST)'
        },
        'environment': Config.ENV,
        'status': 'running'
    })

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
    """Analyze multiple stocks at once"""
    data = request.get_json()
    
    if not data or 'tickers' not in data:
        return jsonify({
            'error': 'Missing tickers',
            'message': 'Please provide tickers in JSON: {"tickers": ["AAPL", "GOOGL"]}'
        }), 400
    
    results = []
    errors = []
    
    for ticker in data['tickers']:
        ticker = ticker.upper()
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
        'failed': len(errors)
    })

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