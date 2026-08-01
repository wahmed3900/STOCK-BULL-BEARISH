def stream_alerts(symbol, news):
    prompt = f"""
    Based on this news for {symbol}, generate alert messages for a trader.
    Focus on big moves, risks, and opportunities.
    """

    stream = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1",
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )

    for chunk in stream:
        token = chunk.choices[0].delta.get("content", "")
        yield token
