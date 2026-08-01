def stream_summary(symbol, news):
    prompt = f"Summarize the latest news for {symbol} in 3–5 bullet points."

    stream = client.chat.completions.create(
        model="meta-llama/Meta-Llama-3.1-70B-Instruct",
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )

    for chunk in stream:
        token = chunk.choices[0].delta.get("content", "")
        yield token
