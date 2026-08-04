@activity.defn
async def analyze_sentiment(symbol: str, news_text: str) -> dict:
    """Analyze sentiment using Together AI"""
    import together
    import os

    # Get API key from environment
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        # Fallback to mock sentiment
        return {
            "symbol": symbol,
            "sentiment_score": 0.65,
            "sentiment_label": "BULLISH",
            "summary": f"Analysis for {symbol} shows positive sentiment"
        }

    client = together.Together(api_key=api_key)

    prompt = f"""
    Analyze the sentiment for {symbol} stock based on this news:
    {news_text}

    Return a JSON with:
    - sentiment_score: float between -1 and 1
    - sentiment_label: BULLISH, BEARISH, or NEUTRAL
    - summary: brief analysis
    """

    response