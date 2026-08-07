import os
import yfinance as yf
from openrouter import OpenRouter
from transformers import pipeline

# ------------------------------
# CONFIGURATION
# ------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable not set!")

client = OpenRouter(api_key=OPENROUTER_API_KEY)

# Initialize local Hugging Face FinBERT pipeline
print("🔄 Loading local FinBERT model (this may take a moment on first run)...")
try:
    hf_analyzer = pipeline("text-classification", model="ProsusAI/finbert")
    print("✅ Local model loaded successfully!")
except Exception as e:
    raise RuntimeError(f"Failed to load Hugging Face pipeline: {e}")

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
    """Fetch current price, basic info, and recent news for a stock."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None, "Price data not available"
        
        # Pull up to 5 recent news headlines for FinBERT
        news_items = stock.news[:5] if stock.news else []
        headlines = [item.get("title") for item in news_items if item.get("title")]

        return {
            "price": price,
            "name": info.get("longName", ticker),
            "currency": info.get("currency", "USD"),
            "headlines": headlines
        }, None
    except Exception as e:
        return None, f"Failed to fetch stock data: {e}"

def compute_local_sentiment(headlines):
    """Analyze news headlines using local FinBERT and compute aggregate sentiment."""
    if not headlines:
        return "No recent news headlines available to analyze."
    
    try:
        # Batch process headlines through Hugging Face pipeline
        results = hf_analyzer(headlines)
        
        pos, neg, neu = 0, 0, 0
        for res in results:
            label = res['label'].lower()
            if label == 'positive': pos += 1
            elif label == 'negative': neg += 1
            else: neu += 1
            
        # Determine aggregate outcome
        if pos > neg: aggregate = "BULLISH (Positive)"
        elif neg > pos: aggregate = "BEARISH (Negative)"
        else: aggregate = "NEUTRAL"
            
        summary = f"{aggregate} -> (Pos: {pos}, Neg: {neg}, Neutral: {neu} across {len(headlines)} headlines)"
        return summary
    except Exception as e:
        return f"Error running local FinBERT: {e}"

def call_ai_model(prompt, model_list=PREFERRED_MODELS):
    """Call OpenRouter with a fallback list of models."""
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
            return response.choices[0].message.content, None
        except Exception as e:
            error_msg = f"Model {model} failed: {str(e)}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
            continue

    return None, f"All models failed! Errors: {'; '.join(errors)}"

def analyze_stock(ticker):
    """Full pipeline: fetch stock data + local FinBERT + OpenRouter analysis."""
    print(f"\n📊 Analyzing {ticker}...")

    # 1. Get stock data
    stock_data, error = get_stock_data(ticker)
    if error:
        print(f"❌ Error: {error}")
        return

    price = stock_data["price"]
    name = stock_data["name"]
    currency = stock_data["currency"]
    headlines = stock_data["headlines"]

    print(f"💰 Price: {currency} {price:.2f}")

    # 2. Compute local FinBERT sentiment
    print("🤖 Processing local FinBERT sentiment...")
    local_sentiment = compute_local_sentiment(headlines)

    # 3. Build the AI prompt for OpenRouter
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

    # 4. Call OpenRouter with fallback
    analysis, error = call_ai_model(prompt)
    if error:
        print(f"❌ OpenRouter AI Error: {error}")
        return

    # 5. Display combined results
    print("\n" + "="*50)
    print(f"📈 COMBINED ANALYSIS: {ticker}")
    print("="*50)
    print(f"💰 Price: {currency} {price:.2f}")
    print(f"🏷️  Name: {name}")
    print(f"\n🎯 LOCAL FINBERT NEWS SENTIMENT:")
    print(f"   {local_sentiment}")
    print("-"*50)
    print("🌐 OPENROUTER AI ANALYSIS:")
    print("-"*50)
    print(analysis)
    print("="*50)

# ------------------------------
# RUN THE TEST
# ------------------------------

if __name__ == "__main__":
    ticker = input("Enter stock ticker (e.g., AMZN, AAPL, TSLA): ").strip().upper()
    if not ticker:
        ticker = "AMZN"  # Default fallback
    analyze_stock(ticker)
