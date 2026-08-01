def allowed_models(subscription):
    if subscription == "starter":
        return ["openrouter/free", "together/llama70b"]
    if subscription == "pro":
        return ["openrouter/free", "together/llama70b", "together/llama405b", "together/deepseek", "together/qwen110b"]

        