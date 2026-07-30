"""
Price data service.
Primary: yfinance (free, no API key, but occasionally rate-limited by Yahoo).
Fallback: Alpha Vantage free tier (needs ALPHA_VANTAGE_API_KEY, 25 requests/day limit).
"""
import os
import requests
import yfinance as yf

ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


def _from_yfinance(ticker: str):
    t = yf.Ticker(ticker)
    hist = t.history(period="5d")
    if hist.empty:
        return None

    last_close = float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_close
    change = last_close - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0

    return {
        "ticker": ticker.upper(),
        "price": round(last_close, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "source": "yfinance",
    }


def _from_alpha_vantage(ticker: str):
    if not ALPHA_VANTAGE_KEY:
        return None

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker,
        "apikey": ALPHA_VANTAGE_KEY,
    }
    resp = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("Global Quote", {})
    if not data or "05. price" not in data:
        return None

    price = float(data["05. price"])
    change = float(data["09. change"])
    change_pct = float(data["10. change percent"].strip("%"))

    return {
        "ticker": ticker.upper(),
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "source": "alpha_vantage",
    }


def get_quote(ticker: str):
    """Try yfinance first, fall back to Alpha Vantage. Returns None if both fail."""
    try:
        quote = _from_yfinance(ticker)
        if quote:
            return quote
    except Exception:
        pass

    try:
        return _from_alpha_vantage(ticker)
    except Exception:
        return None
