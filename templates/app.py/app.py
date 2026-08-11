# stock-dashboard/app.py
import os
import json
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context, session, flash, redirect, url_for
from flask_cors import CORS
from google import genai
from google.genai import types
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Generator, Optional, Dict, Any

# Load .env values
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
CORS(app)

# Load API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

# Initialize Gemini client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash-lite"  # Use flash-lite for faster responses
STREAMING_MODEL = "gemini-2.0-flash-lite"  # Can use different model for streaming

# Mock user data for demo
USER_TIERS = {
    "demo_user": "starter",
    "guest": "free"
}

# ==================== Helper Functions ====================

def fetch_ohlc(symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
    """
    Fetch OHLC (Open, High, Low, Close) data for a symbol.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        
        if hist.empty:
            return {"error": f"No data found for {symbol}"}
        
        # Prepare OHLC data
        ohlc_data = {
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "data": []
        }
        
        for date, row in hist.iterrows():
            ohlc_data["data"].append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"])
            })
        
        # Add current price and change
        if len(ohlc_data["data"]) > 0:
            current = ohlc_data["data"][-1]["close"]
            previous = ohlc_data["data"][-2]["close"] if len(ohlc_data["data"]) > 1 else current
            ohlc_data["current_price"] = current
            ohlc_data["change"] = round(((current - previous) / previous) * 100, 2)
        
        return ohlc_data
        
    except Exception as e:
        logger.error(f"Error fetching OHLC for {symbol}: {e}")
        return {"error": str(e)}

def get_stock_info(symbol: str) -> Dict[str, Any]:
    """
    Get comprehensive stock information.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        return {
            "symbol": symbol,
            "name": info.get("longName", info.get("shortName", symbol)),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "eps": info.get("trailingEps", 0),
            "dividend_yield": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0,
            "52_week_high": info.get("fiftyTwoWeekHigh", 0),
            "52_week_low": info.get("fiftyTwoWeekLow", 0),
            "volume": info.get("volume", 0),
            "avg_volume": info.get("averageVolume", 0),
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0))
        }
    except Exception as e:
        logger.error(f"Error fetching stock info for {symbol}: {e}")
        return {"error": str(e)}

def get_news(symbol: str, limit: int = 5) -> list:
    """
    Get recent news for a symbol.
    """
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news[:limit] if ticker.news else []
        
        formatted_news = []
        for item in news:
            formatted_news.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "publisher": item.get("publisher", ""),
                "providerPublishTime": datetime.fromtimestamp(
                    item.get("providerPublishTime", time.time())
                ).strftime("%Y-%m-%d %H:%M")
            })
        
        return formatted_news
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return []

def get_user_tier(username: str = None) -> str:
    """
    Get user tier from session or mock data.
    """
    if username and username in USER_TIERS:
        return USER_TIERS[username]
    
    # Check session
    user_tier = session.get('user_tier')
    if user_tier:
        return user_tier
    
    return "free"

def create_analysis_prompt(symbol: str, stock_info: Dict, news: list, analysis_type: str = "comprehensive") -> str:
    """
    Create a prompt for Gemini analysis.
    """
    news_text = "\n".join([f"- {item['title']} ({item['publisher']})" for item in news[:5]]) if news else "No recent news available"
    
    prompts = {
        "comprehensive": f"""
You are a financial analyst. Analyze {symbol} stock comprehensively:

COMPANY INFORMATION:
- Name: {stock_info.get('name', symbol)}
- Sector: {stock_info.get('sector', 'N/A')}
- Industry: {stock_info.get('industry', 'N/A')}
- Market Cap: ${stock_info.get('market_cap', 0):,}
- P/E Ratio: {stock_info.get('pe_ratio', 0)}
- EPS: ${stock_info.get('eps', 0)}
- Dividend Yield: {stock_info.get('dividend_yield', 0)}%
- 52-Week High: ${stock_info.get('52_week_high', 0)}
- 52-Week Low: ${stock_info.get('52_week_low', 0)}
- Current Price: ${stock_info.get('current_price', 0)}

RECENT NEWS:
{news_text}

Provide a comprehensive analysis including:
1. **Company Overview**: Brief summary of the company
2. **Financial Health**: Assessment of financial metrics
3. **News Sentiment**: Analysis of recent news impact
4. **Technical Outlook**: Key technical levels and trends
5. **Risks & Opportunities**: Main factors affecting the stock
6. **Recommendation**: Clear Buy/Hold/Sell recommendation with reasoning
""",
        
        "sentiment": f"""
You are a sentiment analyst. Analyze market sentiment for {symbol}:

RECENT NEWS:
{news_text}

KEY METRICS:
- Price: ${stock_info.get('current_price', 0)}
- P/E Ratio: {stock_info.get('pe_ratio', 0)}
- 52-Week Range: ${stock_info.get('52_week_low', 0)} - ${stock_info.get('52_week_high', 0)}

Provide:
1. **Overall Sentiment**: Bullish, Bearish, or Neutral with score (1-10)
2. **News Sentiment Breakdown**: Positive, Negative, Neutral ratio
3. **Market Reaction**: How the market is responding
4. **Short-term Outlook**: Next 1-2 weeks prediction
5. **Key Drivers**: Main factors driving sentiment
""",
        
        "impact": f"""
You are a market impact analyst. Analyze potential market impact for {symbol}:

COMPANY: {stock_info.get('name', symbol)}
SECTOR: {stock_info.get('sector', 'N/A')}
CURRENT PRICE: ${stock_info.get('current_price', 0)}
MARKET CAP: ${stock_info.get('market_cap', 0):,}

RECENT NEWS:
{news_text}

Provide:
1. **Immediate Impact**: Short-term price impact assessment
2. **Sector Impact**: How this affects the sector
3. **Market Implications**: Broader market implications
4. **Key Catalysts**: Main events driving impact
5. **Risk Assessment**: Risk level (Low/Medium/High)
6. **Actionable Insight**: What investors should do
"""
    }
    
    return prompts.get(analysis_type, prompts["comprehensive"])

# ==================== Routes ====================

@app.route('/', methods=['GET'])
@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Main dashboard page."""
    user_name = session.get('user_name', 'Guest')
    tier = get_user_tier()
    
    # Mock stats
    stats = {
        "stocks_tracked": 5 if tier != "free" else 1,
        "analyses_today": 3,
        "portfolio_value": "12,450",
        "alerts_active": 2 if tier != "free" else 0
    }
    
    return render_template(
        'index.html',
        user_name=user_name,
        tier=tier,
        year=datetime.now().year,
        **stats
    )

@app.route('/pricing')
def pricing():
    """Pricing page."""
    return render_template('pricing.html', tier=get_user_tier())

@app.route('/profile')
def profile():
    """User profile page."""
    return render_template('profile.html', user_name=session.get('user_name', 'Guest'))

@app.route('/upgrade', methods=['POST'])
def upgrade_tier():
    """Upgrade user tier."""
    tier = request.form.get('tier', 'free')
    billing_type = request.form.get('billing_type', 'monthly')
    
    # In production, process payment here
    session['user_tier'] = tier
    flash(f'Successfully upgraded to {tier.title()} plan! 🎉', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    """Logout user."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "gemini": "available" if GEMINI_API_KEY else "unavailable",
            "yfinance": "available"
        }
    })

@app.route('/api/validate-ticker', methods=['GET'])
def validate_ticker():
    """Validate a ticker symbol."""
    symbol = request.args.get('symbol', '').upper()
    if not symbol:
        return jsonify({"error": "Symbol parameter required"}), 400
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if info and info.get('symbol'):
            return jsonify({
                "valid": True,
                "symbol": symbol,
                "name": info.get('longName', info.get('shortName', symbol)),
                "exchange": info.get('exchange', 'N/A')
            })
        else:
            return jsonify({"valid": False, "symbol": symbol})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/search-tickers', methods=['GET'])
def search_tickers():
    """Search for tickers by query."""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify({"results": []})
    
    try:
        # Use yfinance to search
        tickers = yf.Tickers(query)
        results = []
        
        # Try to get info for each ticker
        if hasattr(tickers, 'tickers'):
            for symbol, ticker in tickers.tickers.items():
                try:
                    info = ticker.info
                    if info and info.get('symbol'):
                        results.append({
                            "symbol": info.get('symbol'),
                            "name": info.get('longName', info.get('shortName', symbol)),
                            "exchange": info.get('exchange', 'N/A'),
                            "type": info.get('quoteType', 'EQUITY')
                        })
                except:
                    continue
        
        return jsonify({"results": results[:10]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-data', methods=['GET'])
def get_market_data():
    """Get market data for a symbol (Premium feature)."""
    symbol = request.args.get('symbol', '').upper()
    tier = get_user_tier()
    
    if tier == "free":
        return jsonify({"error": "Market data requires Starter or Pro plan"}), 403
    
    if not symbol:
        return jsonify({"error": "Symbol parameter required"}), 400
    
    ohlc_data = fetch_ohlc(symbol)
    if "error" in ohlc_data:
        return jsonify(ohlc_data), 404
    
    return jsonify(ohlc_data)

@app.route('/api/analyze/<ticker>', methods=['GET'])
def analyze_stock(ticker):
    """Analyze stock using Gemini AI."""
    ticker = ticker.upper()
    tier = get_user_tier()
    
    # Check usage limits for free tier
    if tier == "free":
        # In production, track usage per user
        pass
    
    # Get stock data and news
    stock_info = get_stock_info(ticker)
    if "error" in stock_info:
        return jsonify({"error": stock_info["error"]}), 404
    
    news = get_news(ticker, limit=5)
    
    # Create prompt
    prompt = create_analysis_prompt(ticker, stock_info, news, "comprehensive")
    
    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        
        analysis = {
            "ticker": ticker,
            "analysis": response.text,
            "info": stock_info,
            "news": news,
            "timestamp": datetime.now().isoformat(),
            "model": MODEL
        }
        
        return jsonify(analysis)
        
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stream-analyze', methods=['POST'])
def stream_analyze():
    """Stream AI analysis using Gemini."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400
    
    symbol = data.get('symbol', '').upper()
    analysis_type = data.get('analysis_type', 'comprehensive')
    model = data.get('model', STREAMING_MODEL)
    
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
    
    # Get stock info and news
    stock_info = get_stock_info(symbol)
    if "error" in stock_info:
        return jsonify({"error": stock_info["error"]}), 404
    
    news = get_news(symbol, limit=5)
    
    # Create prompt
    prompt = create_analysis_prompt(symbol, stock_info, news, analysis_type)
    
    def generate():
        try:
            # Yield start metadata
            yield f"data: {json.dumps({'type': 'start', 'symbol': symbol, 'model': model, 'analysis_type': analysis_type})}\n\n"
            
            # Stream from Gemini
            response = gemini_client.models.generate_content_stream(
                model=model,
                contents=prompt,
            )
            
            for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"
            
            # Yield end metadata
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error for {symbol}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/stream-analyze-enhanced', methods=['POST'])
def stream_analyze_enhanced():
    """
    Enhanced streaming analysis with Gemini 2.0 features.
    Supports thinking, reasoning, and function calling.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400
    
    symbol = data.get('symbol', '').upper()
    analysis_type = data.get('analysis_type', 'comprehensive')
    model = data.get('model', "gemini-2.0-flash-lite")
    include_reasoning = data.get('include_reasoning', True)
    
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
    
    # Get stock info and news
    stock_info = get_stock_info(symbol)
    if "error" in stock_info:
        return jsonify({"error": stock_info["error"]}), 404
    
    news = get_news(symbol, limit=5)
    prompt = create_analysis_prompt(symbol, stock_info, news, analysis_type)
    
    def generate():
        try:
            yield f"data: {json.dumps({'type': 'start', 'symbol': symbol, 'model': model})}\n\n"
            
            if include_reasoning and "flash" not in model:
                # Use thinking/reasoning features for Pro models
                config = {
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }
                
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                
                # Simulate streaming by splitting response
                words = response.text.split()
                for i in range(0, len(words), 3):
                    chunk = " ".join(words[i:i+3])
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk + ' '})}\n\n"
                    time.sleep(0.02)
            else:
                # Standard streaming
                response = gemini_client.models.generate_content_stream(
                    model=model,
                    contents=prompt,
                )
                
                for chunk in response:
                    if chunk.text:
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"
            
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/model', methods=['GET'])
def get_model_info():
    """Get current model information."""
    return jsonify({
        "model": MODEL,
        "provider": "Google Gemini",
        "available_models": [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ],
        "features": {
            "streaming": True,
            "reasoning": True,
            "function_calling": True,
            "multi_modal": True
        }
    })

@app.route('/chart', methods=['GET'])
def chart():
    """Render chart page."""
    return render_template('chart.html', tier=get_user_tier())

@app.route('/stream/<symbol>', methods=['GET'])
def stream_ticker(symbol):
    """Stream price updates for a ticker (SSE)."""
    def generate():
        while True:
            try:
                data = fetch_ohlc(symbol, period="1d", interval="1m")
                if "error" not in data and data.get("data"):
                    current = data["data"][-1]
                    yield f"data: {json.dumps({'price': current['close'], 'timestamp': current['date']})}\n\n"
                else:
                    yield f"data: {json.dumps({'error': 'No data'})}\n\n"
                time.sleep(60)  # Update every minute
            except Exception as e:
                logger.error(f"Stream error for {symbol}: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                time.sleep(5)
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/gemini-models', methods=['GET'])
def list_gemini_models():
    """List available Gemini models."""
    try:
        models = []
        for model in gemini_client.models.list():
            models.append({
                "name": model.name,
                "display_name": model.display_name,
                "description": model.description,
                "supported_actions": model.supported_actions
            })
        return jsonify({"models": models[:10]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """404 error handler."""
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """500 error handler."""
    logger.error(f"Internal error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# ==================== Main Entry Point ====================

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
