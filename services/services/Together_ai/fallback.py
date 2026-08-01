def stream_with_fallback(symbol, news):
    primary = "deepseek-ai/DeepSeek-R1"
    fallback = "meta-llama/Meta-Llama-3.1-70B-Instruct"

    try:
        stream = client.chat.completions.create(
            model=primary,
            messages=[{"role": "user", "content": f"{symbol} news:\n{news}"}],
            stream=True
        )
    except Exception:
        stream = client.chat.completions.create(
            model=fallback,
            messages=[{"role": "user", "content": f"{symbol} news:\n{news}"}],
            stream=True
        )

    for chunk in stream:
        token = chunk.choices[0].delta.get("content", "")
        yield token
