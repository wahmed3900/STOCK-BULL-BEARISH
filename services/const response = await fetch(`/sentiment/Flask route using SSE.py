import os
from openai import OpenAI

# --- CONFIGURATION ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Set in Render's Environment Variables
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Initialize the OpenRouter client
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL
)

# --- STREAMING FUNCTION ---
def openrouter_stream(symbol: str, news: str, model: str = "deepseek-ai/DeepSeek-R1"):
    """
    Streams step-by-step reasoning from a model (e.g., DeepSeek-R1) via OpenRouter.

    Args:
        symbol (str): The stock symbol or topic (e.g., "AAPL").
        news (str): The news or context to analyze.
        model (str): The model ID (default: "deepseek-ai/DeepSeek-R1").

    Yields:
        str: SSE-formatted chunks of the model's response.
    """
    if not OPENROUTER_API_KEY:
        yield f"data: [ERROR] OpenRouter API key not set in environment variables.\n\n"
        return

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": f"Analyze {symbol} using this news:\n{news}\nGive step-by-step reasoning."
            }],
            stream=True
        )

        for chunk in stream:
            if chunk.choices:
                token = chunk.choices[0].delta.get("content", "")
                if token:
                    yield f"data: {token}\n\n"

    except Exception as e:
        yield f"data: [ERROR] {str(e)}\n\n"
        print(f"Streaming error: {e}")  # Log errors to Render's logs

# --- EXAMPLE USAGE (for testing locally) ---
if __name__ == "__main__":
    # Test the function (only for local testing)
    for token in openrouter_stream(
        symbol="AAPL",
        news="Apple announces a new AI-powered iPhone."
    ):
        print(token, end="")