from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
import re
import yfinance as yf
from functools import lru_cache
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this!

# Cache validation results to avoid rate limits
@lru_cache(maxsize=1000)
def validate_ticker_cached(symbol):
    """Validate if a ticker exists using yfinance"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if info and info.get('symbol'):
            return {
                'valid': True,
                'name': info.get('longName') or info.get('shortName') or symbol,
                'sector': info.get('sector'),
                'industry': info.get('industry')
            }
    except:
        pass
    return {'valid': False}

@app.route('/api/validate-ticker')
def validate_ticker():
    """API endpoint to validate a ticker symbol"""
    symbol = request.args.get('symbol', '').strip().upper()

    # Basic validation
    if not re.match(r'^[A-Z]{1,5}$', symbol):
        return jsonify({'valid': False, 'error': 'Invalid format'})

    # Check cache or fetch
    result = validate_ticker_cached(symbol)
    return jsonify(result)

@app.route('/api/search-tickers')
def search_tickers():
    """Search for tickers matching a query"""
    query = request.args.get('q', '').strip().upper()

    if len(query) < 2:
        return jsonify({'suggestions': []})

    # Common tickers list (you'd typically have this in a database)
    common_tickers = [
        {'symbol': 'AAPL', 'name': 'Apple Inc.'},
        {'symbol': 'MSFT', 'name': 'Microsoft Corporation'},
        {'symbol': 'GOOGL', 'name': 'Alphabet Inc.'},
        {'symbol': 'AMZN', 'name': 'Amazon.com Inc.'},
        {'symbol': 'TSLA', 'name': 'Tesla Inc.'},
        {'symbol': 'META', 'name': 'Meta Platforms Inc.'},
        {'symbol': 'NVDA', 'name': 'NVIDIA Corporation'},
        {'symbol': 'JPM', 'name': 'JPMorgan Chase & Co.'},
        {'symbol': 'VTI', 'name': 'Vanguard Total Stock Market ETF'},
        {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF Trust'},
    ]

    # Filter matches
    matches = [
        t for t in common_tickers
        if t['symbol'].startswith(query) or query in t['name']
    ][:10]

    return jsonify({'suggestions': matches})

@app.route('/')
def dashboard():
    """Main dashboard page"""
    # Your existing dashboard logic
    tier = session.get('tier', 'free')
    return render_template('base.html', tier=tier)

@app.route('/login')
def login():
    # Your Google OAuth login
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('dashboard'))

@app.route('/demo_login')
def demo_login():
    session['user_name'] = 'Demo User'
    session['tier'] = 'premium'
    flash('Logged in as Demo User (Premium Tier)', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)