def analyze_stock(symbol):
    news = fetch_latest_news(symbol)
    prompt = f"Analyze {symbol} based on this news:\n{news}"
    response = client.chat.completions.create(...)
    return response.choices[0].message["content"]
