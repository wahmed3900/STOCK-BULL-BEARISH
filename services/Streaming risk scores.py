def stream_risk(symbol, news):
    prompt = f"""
    Analyze {symbol} based on this news.
    Think step by step about risks.
    At the end, output: RISK_SCORE: 0–100.
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
