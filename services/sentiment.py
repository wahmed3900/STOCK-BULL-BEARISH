import os
import requests
import logging
import time
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FREE_MODELS = [
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "meta-llama/llama-3.2-1b-instruct:free",
    "mistralai/mistral-7b-instruct:free"
]

PROMPT_TEMPLATE = """You are a stock market analyst. Given this price data for {ticker}:
- Current price: ${price}
- Change: {change} ({change_pct}%)

Provide a one-word verdict on the FIRST line only, choosing from: Bullish, Bearish, or Neutral.
Then on the following lines, give a 1-2 sentence plain-English reason.

Example format:
Bullish
Strong upward momentum with high volume indicates buyer interest.
"""

def get_sentiment(
    ticker: str, 
    price: float, 
    change: float, 
    change_pct: float,
    model: str = FREE_MODELS[0],
    max_retries: int = 2
) -> Dict[str, str]:
    """Get AI-powered sentiment analysis for a stock."""
    
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {
            "verdict": "Unavailable", 
            "reason": "Set OPENROUTER_API_KEY to enable AI analysis."
        }
    
    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker, 
        price=round(price, 2), 
        change=round(change, 2), 
        change_pct=round(change_pct, 2)
    )
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.1,  # More deterministic
                },
                timeout=20,
            )
            
            if resp.status_code == 200:
                content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    return parse_and_validate_response(content)
                else:
                    logger.warning(f"Empty response for {ticker}")
                    return {"verdict": "Neutral", "reason": "AI service returned empty content."}
            
            elif resp.status_code in [429, 503] and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            else:
                logger.error(f"API error {resp.status_code}: {resp.text[:200]}")
                return {
                    "verdict": "Unavailable",
                    "reason": f"AI service responded with status {resp.status_code}",
                }
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout for {ticker}")
            if attempt < max_retries - 1:
                continue
            return {"verdict": "Unavailable", "reason": "AI service timeout"}
            
        except Exception as e:
            logger.error(f"Error for {ticker}: {e}")
            if attempt < max_retries - 1:
                continue
            return {"verdict": "Unavailable", "reason": f"AI analysis unavailable: {e}"}
    
    return {"verdict": "Unavailable", "reason": "Max retries exceeded"}

def parse_and_validate_response(content: str) -> Dict[str, str]:
    """Parse and validate the AI response."""
    lines = content.strip().split("\n")
    valid_verdicts = ["Bullish", "Bearish", "Neutral"]
    
    # Get verdict from first line
    verdict = lines[0].strip().strip(".:") if lines else "Neutral"
    
    # Validate verdict
    if verdict not in valid_verdicts:
        for word in verdict.split():
            if word in valid_verdicts:
                verdict = word
                break
        else:
            verdict = "Neutral"
    
    # Get reason from remaining lines
    reason = " ".join(lines[1:]).strip() if len(lines) > 1 else "No detailed reason provided."
    
    return {"verdict": verdict, "reason": reason}
