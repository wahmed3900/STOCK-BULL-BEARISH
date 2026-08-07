#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import io
import requests
import yfinance as yf

# Fix encoding for terminal output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ------------------------------
# CONFIGURATION
# ------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("⚠️  WARNING: OPENROUTER_API_KEY environment variable not set!")
    print("Please run: export OPENROUTER_API_KEY='your-key-here'")

# 🔥 FALLBACK MODEL LIST (in priority order)
PREFERRED_MODELS = [
    "nvidia/nv-remote-3-ultra",          # Best for complex financial analysis
    "ling/ling-3.0-flash",               # Fast sentiment analysis
    "cohere/north-mini-code",            # Backup
    "google/gemini-flash-1.5",           # Extra backup
]

# ------------------------------
# CORE FUNCTIONS
# ------------------------------

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
            "currency": info.get("currency", "USD")
        }, None
    except Exception as e:
        return None, f"Failed to fetch stock data: {e}"

def call_ai_model(prompt, model_list=PREFERRED_MODELS):
    """
    Call OpenRouter with a fallback list of models using the 'requests' library.
    Tries each model in order until one succeeds.
    """
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY is not set. Please export it."

    errors = []

    for model in model_list:
        try:
            print(f"🔄 Trying model: {model}...")

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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

            # Check if request was successful
            if response.status_code == 200:
import sys
import io
import os
import requests
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("⚠️ WARNING: OPENROUTER_API_KEY environment variable not set!")
    print("Please run: export OPENROUTER_API_KEY='your-key-here'")

# Fallback model list for AI analysis
PREFERRED_MODELS = [
    "nvidia/nv-remote-3-ultra",    # Best for complex financial analysis
    "ling/ling-3.0-flash",         # Fast sentiment analysis
    "cohere/north-mini-code",      # Backup
    "google/gemini-flash-1.5",     # Extra backup
]

# ------------------------------
# CORE FUNCTIONS
# ------------------------------

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
            "currency": info.get("currency", "USD")
        }, None
    except Exception as e:
        return None, f"Failed to fetch stock data: {e}"

def call_ai_model(prompt, model_list=PREFERRED_MODELS):
    """Call OpenRouter API with fallback models."""
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY is not set. Please export it."

    errors = []

    for model in model_list:
        try:
            print(f"🔄 Trying model: {model}...")

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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
                print(f"❌ {error_msg}")
                continue

        except requests.exceptions.Timeout:
            error_msg = f"{model}: Request timed out"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue
        except Exception as e:
            error_msg = f"{model}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue

    return None, f"All models failed! Errors: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Analyze a stock: fetch data + AI sentiment analysis."""
    print(f"\n📊 Analyzing {ticker}...")

    # Fetch stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        print(f"❌ Error: {error}")
        return

    price = stock_data["price"]
    name = stock_data["name"]
    currency = stock_data["currency"]

    print(f"💰 Price: {currency} {price:.2f}")

    # Build AI prompt
    prompt = f"""
    Analyze the following stock:
    Ticker: {ticker}
    Company: {name}
    Current Price: {currency} {price:.2f}

    Provide:
    1. A brief sentiment assessment (bullish / bearish / neutral)
    2. The key reason for this sentiment
    3. A 1-2 sentence summary for a dashboard display
    """

    # Call AI model
    analysis, error = call_ai_model(prompt)
    if error:
        print(f"❌ AI Error: {error}")
        return

    # Display results
    print("\n" + "="*50)
    print(f"📈 BULL/BEAR ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {currency} {price:.2f}")
    print(f"🏷️ Name: {name}")
    print("\n🤖 AI Sentiment Analysis:")
    print("-"*50)
    print(analysis)
    print("="*50)

# ------------------------------
# RUN THE ANALYSIS
# ------------------------------

if __name__ == "__main__":
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"  # Default fallback
    analyze_stock(ticker)                result = response.json()
                return result["choices"][0]["message"]["content"], None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                errors.append(f"{model}: {error_msg}")
                print(f"❌ {error_msg}")
                continue

        except requests.exceptions.Timeout:
            error_msg = f"{model}: Request timed out"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue
        except Exception as e:
            error_msg = f"{model}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue

    # If all models fail
    return None, f"All models failed! Errors: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Full pipeline: fetch stock data + AI analysis."""
    print(f"\n📊 Analyzing {ticker}...")

    # 1. Get stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        print(f"❌ Error: {error}")
        return

    price = stock_data["price"]
    name = stock_data["name"]
    currency = stock_data["currency"]

    print(f"💰 Price: {currency} {price:.2f}")

    # 2. Build the AI prompt
    prompt = f"""
    Analyze the following stock:

    Ticker: {ticker}
    Company: {name}
    Current Price: {currency} {price:.2f}

    Please provide:
    1. A brief sentiment assessment (bullish / bearish / neutral)
    2. The key reason for this sentiment
    3. A 1-2 sentence summary for a quick dashboard display

    Keep your response clear and formatted for easy reading.
    """

    # 3. Call AI with fallback
    analysis, error = call_ai_model(prompt)
    if error:
        print(f"❌ AI Error: {error}")
        return

    # 4. Display results
    print("\n" + "="*50)
    print(f"📈 BULL/BEAR ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {currency} {price:.2f}")
    print(f"🏷️  Name: {name}")
    print("\n🤖 AI Sentiment Analysis:")
    print("-"*50)
    print(analysis)
    print("="*50)

# ------------------------------
# RUN THE TEST
# ------------------------------

if __name__ == "__main__":
    # 🧪 Test with a real stock
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"  # Default fallback
    analyze_stock(ticker)            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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

            # Check if request was successful
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"], None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                errors.append(f"{model}: {error_msg}")
                print(f"❌ {error_msg}")
                continue

        except requests.exceptions.Timeout:
            error_msg = f"{model}: Request timed out"
            errors.appendk(error_msg)
            print(f"❌ {error_msg}")
            continue
        except Exception as e:
            error_msg = f"{model}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue

    # If all models fail
    return None, f"All models failed! Errors: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Full pipeline: fetch stock data + AI analysis."""
    print(f"\n📊 Analyzing {ticker}...")
import sys
import io
import os
import requests
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("⚠️ WARNING: OPENROUTER_API_KEY environment variable not set!")
    print("Please run: export OPENROUTER_API_KEY='your-key-here'")

# Fallback model list for AI analysis
PREFERRED_MODELS = [
    "nvidia/nv-remote-3-ultra",    # Best for complex financial analysis
    "ling/ling-3.0-flash",         # Fast sentiment analysis
    "cohere/north-mini-code",      # Backup
    "google/gemini-flash-1.5",     # Extra backup
]

# ------------------------------
# CORE FUNCTIONS
# ------------------------------

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
            "currency": info.get("currency", "USD")
        }, None
    except Exception as e:
        return None, f"Failed to fetch stock data: {e}"

def call_ai_model(prompt, model_list=PREFERRED_MODELS):
    """Call OpenRouter API with fallback models."""
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY is not set. Please export it."

    errors = []

    for model in model_list:
        try:
            print(f"🔄 Trying model: {model}...")

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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
                print(f"❌ {error_msg}")
                continue

        except requests.exceptions.Timeout:
            error_msg = f"{model}: Request timed out"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue
        except Exception as e:
            error_msg = f"{model}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue

    return None, f"All models failed! Errors: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Analyze a stock: fetch data + AI sentiment analysis."""
    print(f"\n📊 Analyzing {ticker}...")

    # Fetch stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        print(f"❌ Error: {error}")
        return

    price = stock_data["price"]
    name = stock_data["name"]
    currency = stock_data["currency"]

    print(f"💰 Price: {currency} {price:.2f}")

    # Build AI prompt
    prompt = f"""
    Analyze the following stock:
    Ticker: {ticker}
    Company: {name}
    Current Price: {currency} {price:.2f}

    Provide:
    1. A brief sentiment assessment (bullish / bearish / neutral)
    2. The key reason for this sentiment
    3. A 1-2 sentence summary for a dashboard display
    """

    # Call AI model
    analysis, error = call_ai_model(prompt)
    if error:
        print(f"❌ AI Error: {error}")
        return

    # Display results
    print("\n" + "="*50)
    print(f"📈 BULL/BEAR ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {currency} {price:.2f}")
    print(f"🏷️ Name: {name}")
    print("\n🤖 AI Sentiment Analysis:")
    print("-"*50)
    print(analysis)
    print("="*50)

# ------------------------------
# RUN THE ANALYSIS
# ------------------------------

if __name__ == "__main__":
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"  # Default fallback
    analyze_stock(ticker)
    # 1. Get stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        print(f"❌ Error: {error}")
        return

    price = stock_data["price"]
    name = stock_data["name"]
    currency = stock_data["currency"]

    print(f"💰 Price: {currency} {price:.2f}")

    # 2. Build the AI prompt
    prompt = f"""
    Analyze the following stock:

    Ticker: {ticker}
    Company: {name}
    Current Price: {currency} {price:.2f}

    Please provide:
    1. A brief sentiment assessment (bullish / bearish / neutral)
    2. The key reason for this sentiment
    3. A 1-2 sentence summary for a quick dashboard display

    Keep your response clear and formatted for easy reading.
    """

    # 3. Call AI with fallback
    analysis, error = call_ai_model(prompt)
    if error:
        print(f"❌ AI Error: {error}")
        return

    # 4. Display results
    print("\n" + "="*50)
    print(f"📈 BULL/BEAR ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {currency} {price:.2f}")
    print(f"🏷️  Name: {name}")
    print("\n🤖 AI Sentiment Analysis:")
    print("-"*50)
    print(analysis)
    print("="*50)

# ------------------------------
# RUN THE TEST
# ------------------------------

if __name__ == "__main__":
    # 🧪 Test with a real stock
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"  # Default fallback
    analyze_stock(ticker)# Fix encoding for terminal output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import requests
import yfinance as yf
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# ------------------------------
# CONFIGURATION
# ------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")


import os
import requests
import yfinance as yf

# ------------------------------
# CONFIGURATION
# ------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("⚠️  WARNING: OPENROUTER_API_KEY environment variable not set!")
    print("Please run: export OPENROUTER_API_KEY='your-key-here'")
    # Let's allow it to run with a placeholder for now, but it will fail later.

# 🔥 FALLBACK MODEL LIST (in priority order)
PREFERRED_MODELS = [
    "nvidia/nv-remote-3-ultra",          # Best for complex financial analysis
    "ling/ling-3.0-flash",               # Fast sentiment analysis
    "cohere/north-mini-code",            # Backup
    "google/gemini-flash-1.5",           # Extra backup
]

# ------------------------------
# CORE FUNCTIONS
# ------------------------------

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
            "currency": info.get("currency", "USD")
        }, None
    except Exception as e:
        return None, f"Failed to fetch stock data: {e}"

def call_ai_model(prompt, model_list=PREFERRED_MODELS):
    """
    Call OpenRouter with a fallback list of models using the 'requests' library.
    Tries each model in order until one succeeds.
    """
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY is not set. Please export it."

    errors = []

    for model in model_list:
        try:
            print(f"🔄 Trying model: {model}...")

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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

            # Check if request was successful
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"], None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                errors.append(f"{model}: {error_msg}")
                print(f"❌ {error_msg}")
                continue  # Try the next model

        except requests.exceptions.Timeout:
            error_msg = f"{model}: Request timed out"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue
        except Exception as e:
            error_msg = f"{model}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue

    # If all models fail
    return None, f"All models failed! Errors: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Full pipeline: fetch stock data + AI analysis."""
    print(f"\n📊 Analyzing {ticker}...")

    # 1. Get stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        print(f"❌ Error: {error}")
        return

    price = stock_data["price"]
    name = stock_data["name"]
    currency = stock_data["currency"]

    print(f"💰 Price: {currency} {price:.2f}")

    # 2. Build the AI prompt
    prompt = f"""
    Analyze the following stock:

    Ticker: {ticker}
    Company: {name}
    Current Price: {currency} {price:.2f}

    Please provide:
    1. A brief sentiment assessment (bullish / bearish / neutral)
    2. The key reason for this sentiment
    3. A 1-2 sentence summary for a quick dashboard display

    Keep your response clear and formatted for easy reading.
    """

    # 3. Call AI with fallback
    analysis, error = call_ai_model(prompt)
    if error:
        print(f"❌ AI Error: {error}")
        return

    # 4. Display results
    print("\n" + "="*50)
    print(f"📈 BULL/BEAR ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {currency} {price:.2f}")
    print(f"🏷️  Name: {name}")
    print("\n🤖 AI Sentiment Analysis:")
    print("-"*50)
    print(analysis)
    print("="*50)

# ------------------------------
# RUN THE TEST
# ------------------------------

if __name__ == "__main__":
    # 🧪 Test with a real stock
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"  # Default fallback
    analyze_stock(ticker)
    


