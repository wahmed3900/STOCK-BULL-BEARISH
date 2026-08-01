def stream_stock_analysis(symbol):
    news = fetch_latest_news(symbol)

    prompt = f"""
    Analyze {symbol} using the latest news below.
    Provide bullish/bearish classification, reasoning, and confidence.
    Stream your thoughts token by token.

    News:
    {news}
    """

    stream = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1",
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )

    for chunk in stream:
        token = chunk.choices[0].delta.get("content", "")
        yield token
