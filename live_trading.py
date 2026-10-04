"""
live_trading.py  —  FastAPI router for live trading via Alpaca (Bot 2)
Mount in main.py:
    from live_trading import router as live_router
    app.include_router(live_router, prefix="/api/live", tags=["live-trading"])
"""
import os
import requests as _requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient

# ---------------------------------------------------------------------------
# Shared DB
# ---------------------------------------------------------------------------
MONGODB_URI     = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "stock_dashboard")
_client         = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
_db             = _client[MONGODB_DB_NAME]

bot2_config_col = _db["bot2_config"]
bot2_runs_col   = _db["bot2_runs"]

# ---------------------------------------------------------------------------
# Alpaca helpers
# ---------------------------------------------------------------------------
ALPACA_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER  = os.getenv("ALPACA_PAPER", "true").lower() == "true"
ALPACA_BASE   = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"
SELF_BASE_URL = os.getenv("SELF_BASE_URL", "http://localhost:8080")

_ALPACA_HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
    "Content-Type":        "application/json",
}


def _alpaca(method: str, path: str, **kwargs):
    url = ALPACA_BASE + path
    r   = _requests.request(method, url, headers=_ALPACA_HEADERS, timeout=15, **kwargs)
    if not r.ok:
        raise HTTPException(r.status_code, r.text)
    return r.json() if r.content else {}


# ---------------------------------------------------------------------------
# Bot 2 default config
# ---------------------------------------------------------------------------
BOT2_DEFAULTS: Dict[str, Any] = {
    "max_positions":        5,
    "risk_pct":             2.0,
    "daily_loss_limit_pct": 3.0,
    "rsi_buy_max":          45.0,
    "rsi_sell_min":         65.0,
    "require_macd":         True,
    "stop_loss_atr":        2.0,
    "take_profit_atr":      4.0,
    "watchlist":            [],
}

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class OrderRequest(BaseModel):
    symbol: str
    qty: float
    side: str = "buy"
    order_type: str = "market"
    time_in_force: str = "day"
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

class Bot2Config(BaseModel):
    max_positions: int           = 5
    risk_pct: float              = 2.0
    daily_loss_limit_pct: float  = 3.0
    rsi_buy_max: float           = 45.0
    rsi_sell_min: float          = 65.0
    require_macd: bool           = True
    stop_loss_atr: float         = 2.0
    take_profit_atr: float       = 4.0
    watchlist: List[str]         = []

class Bot2RunRequest(BaseModel):
    user_id: str
    dry_run: bool = False

# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------
def _compute_rsi(closes, period: int = 14) -> float:
    import numpy as np
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _compute_macd(closes):
    import numpy as np
    def ema(arr, n):
        k, result = 2/(n+1), [arr[0]]
        for v in arr[1:]:
            result.append(v * k + result[-1] * (1 - k))
        return np.array(result)
    if len(closes) < 26:
        return 0.0, 0.0
    e12    = ema(closes, 12)
    e26    = ema(closes, 26)
    macd   = e12 - e26
    signal = ema(macd, 9)
    return macd[-1], signal[-1]


def _compute_atr(highs, lows, closes, period: int = 14) -> float:
    import numpy as np
    if len(closes) < period + 1:
        return 1.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return float(np.mean(trs[-period:]))


def _get_ai_signal(symbol: str) -> str:
    try:
        r = _requests.get(f"{SELF_BASE_URL}/api/analyze/{symbol}", timeout=20)
        if r.ok:
            data = r.json()
            return (data.get("signal") or data.get("recommendation") or "HOLD").upper()
    except Exception:
        pass
    return "HOLD"


# ---------------------------------------------------------------------------
# Routes — Alpaca account / orders
# ---------------------------------------------------------------------------
@router.get("/account")
def get_account():
    return _alpaca("GET", "/v2/account")


@router.get("/positions")
def get_positions():
    return _alpaca("GET", "/v2/positions")


@router.get("/orders")
def get_orders(status: str = "open"):
    return _alpaca("GET", f"/v2/orders?status={status}&limit=50")


@router.post("/order")
def place_order(req: OrderRequest):
    body: Dict[str, Any] = {
        "symbol":        req.symbol.upper(),
        "qty":           str(req.qty),
        "side":          req.side,
        "type":          req.order_type,
        "time_in_force": req.time_in_force,
    }
    if req.stop_loss_price and req.take_profit_price:
        body["order_class"] = "bracket"
        body["stop_loss"]   = {"stop_price": str(round(req.stop_loss_price, 2))}
        body["take_profit"] = {"limit_price": str(round(req.take_profit_price, 2))}
    return _alpaca("POST", "/v2/orders", json=body)


@router.delete("/order/{order_id}")
def cancel_order(order_id: str):
    return _alpaca("DELETE", f"/v2/orders/{order_id}")


@router.delete("/orders/all")
def cancel_all_orders():
    return _alpaca("DELETE", "/v2/orders")


# ---------------------------------------------------------------------------
# Bot 2 config
# ---------------------------------------------------------------------------
@router.get("/bot2/config/{user_id}")
def get_bot2_config(user_id: str):
    cfg = bot2_config_col.find_one({"user_id": user_id}) or {}
    merged = {**BOT2_DEFAULTS, **{k: v for k, v in cfg.items() if k != "_id"}}
    return merged


@router.put("/bot2/config/{user_id}")
def update_bot2_config(user_id: str, cfg: Bot2Config):
    update_data = {**cfg.dict(), "user_id": user_id, "updated_at": datetime.now(timezone.utc)}
    bot2_config_col.update_one({"user_id": user_id}, {"$set": update_data}, upsert=True)
    return {"message": "Config saved"}


# ---------------------------------------------------------------------------
# Bot 2 run
# ---------------------------------------------------------------------------
@router.post("/bot2/run/{user_id}")
def run_bot2(user_id: str, dry_run: bool = False):
    import yfinance as yf
    import numpy as np

    # Load config
    raw_cfg   = bot2_config_col.find_one({"user_id": user_id}) or {}
    cfg       = {**BOT2_DEFAULTS, **{k: v for k, v in raw_cfg.items() if k != "_id"}}
    watchlist = cfg.get("watchlist") or []
    if not watchlist:
        raise HTTPException(400, "Watchlist is empty — add symbols to Bot 2 config first")

    # Alpaca account state
    acct         = _alpaca("GET", "/v2/account")
    equity       = float(acct["equity"])
    open_pos_map = {p["symbol"]: p for p in _alpaca("GET", "/v2/positions")}
    open_count   = len(open_pos_map)

    # Daily P&L check
    daily_pnl_pct = (float(acct["equity"]) - float(acct["last_equity"])) / float(acct["last_equity"]) * 100
    loss_limit    = -abs(cfg["daily_loss_limit_pct"])
    run_log       = []

    for symbol in watchlist:
        entry = {"symbol": symbol, "action": "skip", "reason": ""}
        try:
            ticker    = yf.Ticker(symbol)
            hist      = ticker.history(period="3mo", interval="1d")
            if hist.empty:
                entry["reason"] = "no data"
                run_log.append(entry)
                continue

            closes = hist["Close"].values
            highs  = hist["High"].values
            lows   = hist["Low"].values
            price  = float(closes[-1])

            rsi          = _compute_rsi(closes)
            macd, signal = _compute_macd(closes)
            atr          = _compute_atr(highs, lows, closes)
            ai_signal    = _get_ai_signal(symbol)

            entry["price"]  = round(price, 2)
            entry["rsi"]    = round(rsi, 1)
            entry["macd"]   = round(float(macd), 4)
            entry["signal"] = round(float(signal), 4)
            entry["atr"]    = round(atr, 4)
            entry["ai"]     = ai_signal

            # --- ENTRY ---
            if symbol.upper() not in open_pos_map:
                macd_ok = (macd > signal) if cfg["require_macd"] else True
                if (ai_signal == "BUY"
                        and rsi < cfg["rsi_buy_max"]
                        and macd_ok
                        and open_count < cfg["max_positions"]
                        and daily_pnl_pct > loss_limit):

                    stop_price   = price - cfg["stop_loss_atr"]  * atr
                    target_price = price + cfg["take_profit_atr"] * atr
                    risk_per_share = price - stop_price
                    qty = int((equity * cfg["risk_pct"] / 100) / risk_per_share) if risk_per_share > 0 else 0

                    if qty >= 1:
                        if not dry_run:
                            _alpaca("POST", "/v2/orders", json={
                                "symbol":        symbol.upper(),
                                "qty":           str(qty),
                                "side":          "buy",
                                "type":          "market",
                                "time_in_force": "day",
                                "order_class":   "bracket",
                                "stop_loss":     {"stop_price": str(round(stop_price, 2))},
                                "take_profit":   {"limit_price": str(round(target_price, 2))},
                            })
                            open_count += 1
                        entry["action"] = f"BUY {qty} shares"
                        entry["stop"]   = round(stop_price, 2)
                        entry["target"] = round(target_price, 2)
                    else:
                        entry["reason"] = "qty < 1"
                else:
                    reasons = []
                    if ai_signal != "BUY":           reasons.append(f"AI={ai_signal}")
                    if rsi >= cfg["rsi_buy_max"]:    reasons.append(f"RSI={rsi:.1f}")
                    if not macd_ok:                  reasons.append("MACD<signal")
                    if open_count >= cfg["max_positions"]: reasons.append("max_positions")
                    if daily_pnl_pct <= loss_limit:  reasons.append("daily_loss_limit")
                    entry["reason"] = ", ".join(reasons) or "no signal"

            # --- EXIT ---
            else:
                if ai_signal == "SELL" or rsi > cfg["rsi_sell_min"]:
                    pos_qty = float(open_pos_map[symbol.upper()]["qty"])
                    if not dry_run:
                        _alpaca("POST", "/v2/orders", json={
                            "symbol": symbol.upper(), "qty": str(pos_qty),
                            "side": "sell", "type": "market", "time_in_force": "day",
                        })
                        open_count -= 1
                    entry["action"] = f"SELL {pos_qty} shares"
                    entry["reason"] = f"AI={ai_signal}, RSI={rsi:.1f}"
                else:
                    entry["action"] = "hold"
                    entry["reason"] = f"RSI={rsi:.1f}, AI={ai_signal}"

        except HTTPException as e:
            entry["reason"] = f"alpaca error: {e.detail}"
        except Exception as e:
            entry["reason"] = str(e)

        run_log.append(entry)

    # Save run record
    run_record = {
        "user_id":        user_id,
        "dry_run":        dry_run,
        "ran_at":         datetime.now(timezone.utc),
        "daily_pnl_pct":  round(daily_pnl_pct, 2),
        "equity":         equity,
        "results":        run_log,
    }
    bot2_runs_col.insert_one(run_record)
    return {"dry_run": dry_run, "equity": equity, "daily_pnl_pct": round(daily_pnl_pct, 2), "results": run_log}


@router.get("/bot2/runs/{user_id}")
def get_bot2_runs(user_id: str, limit: int = 20):
    runs = list(bot2_runs_col.find({"user_id": user_id}).sort("ran_at", -1).limit(limit))
    return [{ **r, "_id": str(r["_id"]) } for r in runs]


@router.post("/bot2/liquidate/{user_id}")
def liquidate_all(user_id: str):
    """Emergency — close every open Alpaca position."""
    positions = _alpaca("GET", "/v2/positions")
    cancelled = []
    for pos in positions:
        try:
            _alpaca("DELETE", f"/v2/positions/{pos['symbol']}")
            cancelled.append(pos["symbol"])
        except Exception as e:
            cancelled.append(f"{pos['symbol']}(err:{e})")
    return {"liquidated": cancelled}
