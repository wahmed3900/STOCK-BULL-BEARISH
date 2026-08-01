def stream_multi_model(symbol, news):
    models = [
        "deepseek-ai/DeepSeek-R1",              # reasoning
        "meta-llama/Meta-Llama-3.1-70B-Instruct"  # general sentiment
    ]

    for model in models:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"{symbol} news:\n{news}"}],
            stream=True
        )
        for chunk in stream:
            token = chunk.choices[0].delta.get("content", "")
            yield f"[{model}] {token}"
