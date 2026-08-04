"""
Bull/Bearish AI analysis via OpenRouter, using a free-tier model.
Requires OPENROUTER_API_KEY (get one free at https://openrouter.ai/keys).

Free models change over time - check https://openrouter.ai/models?max_price=0
for the current list and swap MODEL below if this one is retired.
"""
import os
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"

PROMPT_TEMPLATE = """You are a stock market analyst. Given this price data for {ticker}:
- Current price: ${price}
- Change: {change} ({change_pct}%)

Give a one-word verdict on the FIRST line: either "Bullish" or "Bearish" or "Neutral".
Then on the next line, give a 1-2 sentence plain-English reason, based only on this
price movement (do not invent other data you don't have).
"""


def get_sentiment(ticker: str, price: float, change: float, change_pct: float):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {"verdict": "Unavailable", "reason": "Set OPENROUTER_API_KEY to enable AI analysis."}

    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker, price=price, change=change, change_pct=change_pct
    )

    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return {
                "verdict": "Unavailable",
                "reason": f"AI service responded with status {resp.status_code}: {resp.text[:200]}",
            }

        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            return {"verdict": "Unavailable", "reason": "AI service returned no usable content."}

        lines = content.split("\n", 1)
        verdict = lines[0].strip().strip(".")
        reason = lines[1].strip() if len(lines) > 1 else ""

        return {"verdict": verdict, "reason": reason}
    except Exception as e:
        return {"verdict": "Unavailable", "reason": f"AI analysis unavailable: {e}"}
