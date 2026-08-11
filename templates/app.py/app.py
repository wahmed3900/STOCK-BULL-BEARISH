# stock-dashboard/app.py
import os
import json
import time
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from flask_cors import CORS
from google import genai
import yfinance as yf

# Load .env values
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Load Gemini key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash-lite"

# ... (all your function definitions and route decorators go here) ...

def fetch_ohlc(symbol, period="1mo", interval="1d"):
    # ... your function code ...

@app.route('/', methods=['GET'])
@app.route('/dashboard', methods=['GET'])
def dashboard():
    # ... your code ...

@app.route('/health', methods=['GET'])
def health():
    # ... your code ...

@app.route('/chart', methods=['GET'])
def chart():
    # ... your code ...

@app.route('/api/analyze/<ticker>', methods=['GET'])
def analyze_stock(ticker):
    # ... your code ...

@app.route('/stream/<symbol>', methods=['GET'])
def stream_ticker(symbol):
    # ... your code ...

@app.errorhandler(404)
def not_found(_error):
    # ... your code ...

# ⬇️⬇️⬇️ PUT IT HERE - AT THE VERY BOTTOM ⬇️⬇️⬇️
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
