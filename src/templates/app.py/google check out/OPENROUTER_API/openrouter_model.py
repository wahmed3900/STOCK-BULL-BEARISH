import os
import yfinance as yf
from openrouter import OpenRouter

# ------------------------------
# CONFIGURATION
# ------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable not set!")

client = OpenRouter(api_key=OPENROUTER_API_KEY)

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
    Call OpenRouter with a fallback list of models.
    Tries each model in order until one succeeds.
    """
    errors = []

    for model in model_list:
        try:
            print(f"🔄 Trying model: {model}...")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst. Provide concise, actionable stock analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            # Extract the response text
            return response.choices[0].message.content, None
        except Exception as e:
            error_msg = f"Model {model} failed: {str(e)}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
            continue  # Try the next model

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


