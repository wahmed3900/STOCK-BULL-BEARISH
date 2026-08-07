import os
import logging
import sys
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Import your AI logic from the services folder
from services.sentiment import analyze_sentiment

# ----------------------------------------------------------------------
# 1. Logging Configuration
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 2. Load Environment Variables
# ----------------------------------------------------------------------
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# Fail fast if any required key is missing (adjust as needed)
# Assuming at least one key must be present for sentiment analysis
if not OPENROUTER_API_KEY and not TOGETHER_API_KEY:
    logger.critical("No API keys found (OPENROUTER_API_KEY or TOGETHER_API_KEY). Exiting.")
    sys.exit(1)
else:
    logger.info("API keys loaded successfully.")

# ----------------------------------------------------------------------
# 3. Flask App Initialization
# ----------------------------------------------------------------------
app = Flask(__name__)

# Optionally enable CORS (uncomment if needed)
# from flask_cors import CORS
# CORS(app)

# ----------------------------------------------------------------------
# 4. Health Check Endpoint
# ----------------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

# ----------------------------------------------------------------------
# 5. Sentiment Analysis Endpoint
# ----------------------------------------------------------------------
@app.route('/api/sentiment', methods=['POST'])
def sentiment_endpoint():
    """
    Expects a JSON payload:
    {
        "symbol": "AAPL",
        "news": ["Some news text", "Another news item"]
    }
    Returns:
        {
            "symbol": "AAPL",
            "sentiment": { ... }   # whatever analyze_sentiment returns
        }
    """
    # 5a. Parse and validate JSON
    data = request.get_json()
    if data is None:
        logger.warning("Invalid or missing JSON in request")
        return jsonify({"error": "Request body must be valid JSON"}), 400

    symbol = data.get('symbol')
    news = data.get('news')

    # 5b. Validate symbol
    if not symbol or not isinstance(symbol, str) or len(symbol.strip()) == 0:
        logger.warning("Missing or invalid symbol")
        return jsonify({"error": "Symbol must be a non-empty string"}), 400

    # 5c. Validate news
    if not news:
        logger.warning("Missing news data")
        return jsonify({"error": "News data is required"}), 400

    # Allow news as a single string or a list of strings
    if isinstance(news, str):
        news = [news]  # normalize to list
    elif isinstance(news, list):
        # Ensure all elements are strings and non-empty
        if not all(isinstance(item, str) and len(item.strip()) > 0 for item in news):
            logger.warning("News list contains invalid items (must be non-empty strings)")
            return jsonify({"error": "All news items must be non-empty strings"}), 400
    else:
        logger.warning("News must be a string or list of strings")
        return jsonify({"error": "News must be a string or list of strings"}), 400

    # 5d. Call the AI function with error handling
    try:
        logger.info(f"Processing sentiment for symbol: {symbol}, with {len(news)} news items")
        result = analyze_sentiment(symbol, news)
        logger.info(f"Sentiment analysis completed for {symbol}")
    except Exception as e:
        logger.error(f"Error in analyze_sentiment for {symbol}: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error during sentiment analysis"}), 500

    # 5e. Return successful response
    return jsonify({
        "symbol": symbol,
        "sentiment": result
    }), 200

# ----------------------------------------------------------------------
# 6. Error Handlers for Common HTTP Errors
# ----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

# ----------------------------------------------------------------------
# 7. Run the Application
# ----------------------------------------------------------------------
if __name__ == '__main__':
    # Read host and port from environment, with defaults
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    logger.info(f"Starting Flask app on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)