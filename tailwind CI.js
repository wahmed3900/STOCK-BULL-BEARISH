"""
AI Bull/Bearish sentiment analysis using OpenRouter.

Model: meta-llama/llama-3.3-70b-instruct:free
You may swap models anytime:
https://openrouter.ai/models?max_price=0
"""

import os
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

MODEL = "meta-llama/llama-3.3-70b-instruct:free"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
}


def get_sentiment(ticker, price, change, change_pct):
    """
    Returns a dict:
    {
        "verdict": "Bullish" | "Bearish" | "Neutral",
        "reason": "Explanation text"
    }

    Always returns safe fallback if API fails.
    """

    # Safety: if price data missing, return fallback
    if price is None:
        return {
            "verdict": "Neutral",
            "reason": "Price data unavailable."
        }

    prompt = f"""
You are a financial sentiment model. Analyze the stock {ticker}.

Price: {price}
Change: {change}
Percent Change: {change_pct}

Return ONLY a JSON object with:
- verdict: Bullish, Bearish, or Neutral
- reason: a short explanation
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=20
        )

        data = response.json()

        # Extract model output
        raw = data["choices"][0]["message"]["content"]

        # Attempt to parse JSON safely
        import json
        try:
            parsed = json.loads(raw)
        except Exception:
            # If model returns text instead of JSON
            return {
                "verdict": "Neutral",
                "reason": raw.strip()[:200]
            }

        verdict = parsed.get("verdict", "Neutral")
        reason = parsed.get("reason", "No reason provided.")

        return {
            "verdict": verdict,
            "reason": reason
        }

    except Exception as e:
        # Full fallback if API fails
        return {
            "verdict": "Neutral",
            "reason": f"AI unavailable ({str(e)[:80]})."
        }

input.css      ← contains @tailwind base; @tailwind components; @tailwind utilities;
static/css/tailwind.css  ← compiled output

