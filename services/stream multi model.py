from openai import OpenAI  # Replace with your provider's SDK

client = OpenAI(api_key="3e8eed1b0984d056ccf7004de605d29ab3787bc4f2d2af4d18285d1457d4bf58")  # Initialize your client

def stream_multi_model(symbol, news):
    models = [
        "deepseek-ai/DeepSeek-R1",
        "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "qwen/Qwen2.5-72B-Instruct"
    ]

    for model in models:
        yield f"data: [MODEL START] {model}\n\n"

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": f"{symbol} news:\n{news}"}],
                stream=True
            )

            for chunk in stream:
                token = chunk.choices[0].delta.get("content", "")
                if token:
                    yield f"data: {model}: {token}\n\n"

        except Exception as e:
            yield f"data: [ERROR] {model}: {str(e)}\n\n"

        yield f"data: [MODEL END] {model}\n\n"

        