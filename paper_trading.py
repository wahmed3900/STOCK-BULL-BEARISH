"""
paper_trading.py  —  FastAPI router for paper trading (Bot 1)
Mount in main.py:
    from paper_trading import router as paper_router
    app.include_router(paper_router, prefix="/api/paper", tags=["paper-trading"])
"""
import os
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient

MONGODB_URI     = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "stock_dashboard")
_client         = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
_db             = _client[MONGODB_DB_NAME]

paper_accounts  = _db["paper_accounts"]
paper_positions = _db["paper_positions"]
paper_trades    = _db["paper_trades"]

STARTING_CASH = 100_000.0
SELF_BASE_URL = os.getenv("SELF_BASE_URL", "http://localhost:8080")

router = APIRouter()

class OpenPositionRequest(BaseModel):
    user_id: str
    symbol: str
    qty: float
    price: float
    side: str = "buy"
    source: str = "manual"

class BotRunRequest(BaseModel):
    user_id: str
    watchlist: List[str]
    ai_source: str = "gemini"
    dry_run: bool = False

def _get_or_create_account(user_id: str) -> Dict:
    acc = paper_accounts.find_one({"user_id": user_id})
    if not acc:
        acc = {"user_id": user_id, "cash": STARTING_CASH, "total_equity": STARTING_CASH, "created_at": datetime.now(timezone.utc)}
        paper_accounts.insert_one(acc)
    return acc

def _get_ai_signal(symbol: str, ai_source: str = "gemini") -> str:
    try:
        r = requests.get(f"{SELF_BASE_URL}/api/analyze/{symbol}", timeout=20, params={"source": ai_source})
        if r.ok:
            data = r.json()
            sig = data.get("signal") or data.get("recommendation") or ""
            return sig.upper()
    except Exception:
        pass
    return "HOLD"

@router.get("/portfolio/{user_id}")
def get_portfolio(user_id: str):
    import yfinance as yf
    acc = _get_or_create_account(user_id)
    positions = list(paper_positions.find({"user_id": user_id, "status": "open"}))
    market_value = 0.0
    for p in positions:
        try:
            price = yf.Ticker(p["symbol"]).fast_info.get("last_price") or p["entry_price"]
        except Exception:
            price = p["entry_price"]
        p["current_price"] = price
        p["market_value"] = price * p["qty"]
        p["unrealized_pnl"] = (price - p["entry_price"]) * p["qty"]
        market_value += p["market_value"]
    total_equity = acc["cash"] + market_value
    paper_accounts.update_one({"user_id": user_id}, {"$set": {"total_equity": total_equity}})
    return {"cash": acc["cash"], "market_value": market_value, "total_equity": total_equity,
            "positions": [{**p, "_id": str(p["_id"])} for p in positions]}

@router.get("/positions/{user_id}")
def get_positions(user_id: str):
    positions = list(paper_positions.find({"user_id": user_id, "status": "open"}))
    return [{**p, "_id": str(p["_id"])} for p in positions]

@router.post("/positions/open")
def open_position(req: OpenPositionRequest):
    acc = _get_or_create_account(req.user_id)
    cost = req.qty * req.price
    if cost > acc["cash"]:
        raise HTTPException(400, "Insufficient paper-trading cash")
    paper_accounts.update_one({"user_id": req.user_id}, {"$inc": {"cash": -cost}})
    pos = {"user_id": req.user_id, "symbol": req.symbol.upper(), "qty": req.qty,
           "entry_price": req.price, "side": req.side, "source": req.source,
           "status": "open", "opened_at": datetime.now(timezone.utc)}
    result = paper_positions.insert_one(pos)
    return {"position_id": str(result.inserted_id), "cost": cost}

@router.post("/positions/{position_id}/close")
def close_position(position_id: str, exit_price: float):
    try:
        oid = ObjectId(position_id)
    except Exception:
        raise HTTPException(400, "Invalid position ID")
    pos = paper_positions.find_one({"_id": oid, "status": "open"})
    if not pos:
        raise HTTPException(404, "Open position not found")
    proceeds = exit_price * pos["qty"]
    pnl = (exit_price - pos["entry_price"]) * pos["qty"]
    paper_positions.update_one({"_id": oid}, {"$set": {"status": "closed", "exit_price": exit_price, "closed_at": datetime.now(timezone.utc)}})
    paper_accounts.update_one({"user_id": pos["user_id"]}, {"$inc": {"cash": proceeds}})
    paper_trades.insert_one({**pos, "position_id": str(oid), "exit_price": exit_price, "pnl": pnl, "closed_at": datetime.now(timezone.utc)})
    return {"pnl": pnl, "proceeds": proceeds}

@router.get("/trades/{user_id}")
def get_trades(user_id: str, limit: int = 50):
    trades = list(paper_trades.find({"user_id": user_id}).sort("closed_at", -1).limit(limit))
    return [{**t, "_id": str(t["_id"])} for t in trades]

@router.post("/bot/run")
def run_bot1(req: BotRunRequest):
    import yfinance as yf
    acc = _get_or_create_account(req.user_id)
    cash = acc["cash"]
    results = []
    for symbol in req.watchlist:
        signal = _get_ai_signal(symbol, req.ai_source)
        action = "skip"
        if signal == "BUY" and cash > 0:
            try:
                price = yf.Ticker(symbol).fast_info.get("last_price")
                if price and price > 0:
                    qty = int(cash * 0.05 / price)
                    if qty >= 1 and not req.dry_run:
                        cost = qty * price
                        paper_positions.insert_one({"user_id": req.user_id, "symbol": symbol.upper(),
                            "qty": qty, "entry_price": price, "side": "buy", "source": "bot1",
                            "status": "open", "opened_at": datetime.now(timezone.utc)})
                        paper_accounts.update_one({"user_id": req.user_id}, {"$inc": {"cash": -cost}})
                        cash -= cost
                        action = f"bought {qty} @ {price:.2f}"
            except Exception as e:
                action = f"error: {e}"
        elif signal == "SELL":
            for pos in list(paper_positions.find({"user_id": req.user_id, "symbol": symbol.upper(), "status": "open"})):
                try:
                    price = yf.Ticker(symbol).fast_info.get("last_price") or pos["entry_price"]
                    if not req.dry_run:
                        proceeds = price * pos["qty"]
                        pnl = (price - pos["entry_price"]) * pos["qty"]
                        paper_positions.update_one({"_id": pos["_id"]}, {"$set": {"status": "closed", "exit_price": price, "closed_at": datetime.now(timezone.utc)}})
                        paper_accounts.update_one({"user_id": req.user_id}, {"$inc": {"cash": proceeds}})
                        paper_trades.insert_one({**pos, "position_id": str(pos["_id"]), "exit_price": price, "pnl": pnl, "closed_at": datetime.now(timezone.utc)})
                        cash += proceeds
                    action = f"sold {pos['qty']} @ {price:.2f}"
                except Exception as e:
                    action = f"error: {e}"
        results.append({"symbol": symbol, "signal": signal, "action": action})
    return {"results": results, "dry_run": req.dry_run}

@router.post("/account/{user_id}/reset")
def reset_account(user_id: str):
    paper_positions.update_many({"user_id": user_id}, {"$set": {"status": "closed"}})
    paper_accounts.update_one({"user_id": user_id}, {"$set": {"cash": STARTING_CASH, "total_equity": STARTING_CASH}}, upsert=True)
    return {"message": "Account reset to $100,000"}
