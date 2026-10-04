"""
paper_trading.py — Flask Blueprint for paper trading (Bot 1)
Register in app.py:
    from paper_trading import paper_bp
    app.register_blueprint(paper_bp, url_prefix='/api/paper')
"""

import os
import requests
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, request, jsonify
from pymongo import MongoClient

paper_bp = Blueprint("paper", __name__)

# ── DB ────────────────────────────────────────────────────────────────────

MONGO_URI   = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME     = os.getenv("MONGO_DB_NAME", "stockai")
BACKEND_URL = os.getenv("SELF_BASE_URL", "http://localhost:5000")
STARTING_CASH = 100_000.0

_client = None

def _db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client[DB_NAME]

# ── Helpers ───────────────────────────────────────────────────────────────

def _get_price(symbol):
    try:
        r = requests.get(f"{BACKEND_URL}/api/quote/{symbol}", timeout=10)
        d = r.json()
        return float(d.get("price") or d.get("regularMarketPrice") or 0)
    except Exception:
        return 0.0

def _get_signal(symbol):
    try:
        r = requests.get(f"{BACKEND_URL}/api/analyze/{symbol}", timeout=20)
        d = r.json()
        rec = (d.get("recommendation") or d.get("signal") or "HOLD").upper()
        return rec if rec in ("BUY", "SELL", "HOLD") else "HOLD"
    except Exception:
        return "HOLD"

def _get_cash(user_id):
    doc = _db()["paper_accounts"].find_one({"user_id": user_id})
    if not doc:
        _db()["paper_accounts"].insert_one({
            "user_id": user_id, "cash": STARTING_CASH,
            "created_at": datetime.now(timezone.utc)
        })
        return STARTING_CASH
    return float(doc["cash"])

def _set_cash(user_id, amount):
    _db()["paper_accounts"].update_one(
        {"user_id": user_id}, {"$set": {"cash": amount}}, upsert=True
    )

def _clean(doc):
    doc = dict(doc)
    doc.pop("_id", None)
    return doc

# ── Routes ────────────────────────────────────────────────────────────────

@paper_bp.route("/portfolio/<user_id>")
def get_portfolio(user_id):
    cash = _get_cash(user_id)
    positions = list(_db()["paper_positions"].find(
        {"user_id": user_id, "status": "open"}
    ))

    unrealized = 0.0
    open_value = 0.0
    for p in positions:
        price = _get_price(p["symbol"])
        mult = 1 if p["side"] == "buy" else -1
        unrealized += mult * (price - p["entry_price"]) * p["qty"]
        open_value += price * p["qty"]
        p["current_price"] = price
        p["unrealized_pnl"] = mult * (price - p["entry_price"]) * p["qty"]

    closed = list(_db()["paper_trades"].find({"user_id": user_id}))
    realized = sum(t["pnl"] for t in closed)
    wins = sum(1 for t in closed if t["pnl"] > 0)
    win_rate = (wins / len(closed) * 100) if closed else 0.0

    best  = max(closed, key=lambda t: t["pnl"], default=None)
    worst = min(closed, key=lambda t: t["pnl"], default=None)

    return jsonify({
        "user_id": user_id,
        "cash_balance": cash,
        "open_positions": [_clean(p) for p in positions],
        "total_open_value": open_value,
        "unrealized_pnl": unrealized,
        "realized_pnl": realized,
        "total_trades": len(closed),
        "win_rate": win_rate,
        "best_trade": _clean(best) if best else None,
        "worst_trade": _clean(worst) if worst else None,
    })


@paper_bp.route("/positions/<user_id>")
def list_positions(user_id):
    docs = list(_db()["paper_positions"].find(
        {"user_id": user_id, "status": "open"}
    ).sort("entry_time", -1).limit(200))
    return jsonify([_clean(d) for d in docs])


@paper_bp.route("/positions/open", methods=["POST"])
def open_position():
    data = request.json
    user_id = data["user_id"]
    symbol  = data["symbol"].upper()
    side    = data.get("side", "buy")
    qty     = float(data.get("qty", 1))
    price   = float(data.get("entry_price", 0)) or _get_price(symbol)
    cost    = price * qty

    cash = _get_cash(user_id)
    if side == "buy" and cash < cost:
        return jsonify({"error": "Insufficient paper cash"}), 400

    pos = {
        "id": str(uuid4()),
        "user_id": user_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "entry_price": price,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "stop_loss": data.get("stop_loss"),
        "take_profit": data.get("take_profit"),
        "source": data.get("source", "manual"),
        "notes": data.get("notes"),
        "status": "open",
    }
    _db()["paper_positions"].insert_one(pos)
    new_cash = cash - cost if side == "buy" else cash + cost
    _set_cash(user_id, new_cash)
    return jsonify(_clean(pos)), 201


@paper_bp.route("/positions/<position_id>/close", methods=["POST"])
def close_position(position_id):
    data = request.json or {}
    doc  = _db()["paper_positions"].find_one({"id": position_id, "status": "open"})
    if not doc:
        return jsonify({"error": "Position not found"}), 404

    exit_price = float(data.get("exit_price", 0)) or _get_price(doc["symbol"])
    mult = 1 if doc["side"] == "buy" else -1
    pnl  = mult * (exit_price - doc["entry_price"]) * doc["qty"]
    pnl_pct = pnl / (doc["entry_price"] * doc["qty"]) * 100

    trade = {
        "id": str(uuid4()),
        "position_id": position_id,
        "user_id": doc["user_id"],
        "symbol": doc["symbol"],
        "side": doc["side"],
        "qty": doc["qty"],
        "entry_price": doc["entry_price"],
        "exit_price": exit_price,
        "entry_time": doc["entry_time"],
        "exit_time": datetime.now(timezone.utc).isoformat(),
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "source": doc.get("source", "manual"),
        "notes": data.get("notes"),
    }
    _db()["paper_trades"].insert_one(trade)
    _db()["paper_positions"].update_one(
        {"id": position_id}, {"$set": {"status": "closed"}}
    )

    cash = _get_cash(doc["user_id"])
    proceeds = exit_price * doc["qty"]
    new_cash = cash + proceeds if doc["side"] == "buy" else cash - proceeds + pnl
    _set_cash(doc["user_id"], new_cash)

    return jsonify({"closed": True, "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)})


@paper_bp.route("/trades/<user_id>")
def list_trades(user_id):
    limit = int(request.args.get("limit", 50))
    skip  = int(request.args.get("skip", 0))
    docs  = list(_db()["paper_trades"].find({"user_id": user_id})
                 .sort("exit_time", -1).skip(skip).limit(limit))
    return jsonify([_clean(d) for d in docs])


@paper_bp.route("/bot/run", methods=["POST"])
def run_bot():
    data     = request.json
    user_id  = data["user_id"]
    symbols  = data.get("symbols", [])
    source   = data.get("source", "gemini")
    dry_run  = data.get("dry_run", True)
    log      = []

    for symbol in symbols:
        symbol = symbol.upper()
        signal = _get_signal(symbol)
        entry  = {"symbol": symbol, "signal": signal, "action": "none", "detail": ""}
        existing = _db()["paper_positions"].find_one(
            {"user_id": user_id, "symbol": symbol, "status": "open"}
        )

        if signal == "BUY" and not existing:
            if dry_run:
                entry["action"] = "would_buy"
                entry["detail"] = "Would open BUY"
            else:
                price = _get_price(symbol)
                cash  = _get_cash(user_id)
                qty   = max(1.0, round((cash * 0.05) / price, 2))
                req_data = {"user_id": user_id, "symbol": symbol, "side": "buy",
                            "qty": qty, "entry_price": price, "source": source}
                with paper_bp.open_resource("") if False else open("/dev/null"):
                    pass
                # Call open_position logic directly
                cost = price * qty
                pos = {
                    "id": str(uuid4()), "user_id": user_id, "symbol": symbol,
                    "side": "buy", "qty": qty, "entry_price": price,
                    "entry_time": datetime.now(timezone.utc).isoformat(),
                    "source": source, "status": "open",
                }
                _db()["paper_positions"].insert_one(pos)
                _set_cash(user_id, cash - cost)
                entry["action"] = "opened_buy"
                entry["detail"] = f"Bought {qty} @ ${price:.2f}"

        elif signal == "SELL" and existing:
            if dry_run:
                entry["action"] = "would_sell"
                entry["detail"] = "Would close position"
            else:
                price  = _get_price(symbol)
                pos_id = existing.get("id", "")
                mult   = 1 if existing["side"] == "buy" else -1
                pnl    = mult * (price - existing["entry_price"]) * existing["qty"]
                _db()["paper_trades"].insert_one({
                    "id": str(uuid4()), "position_id": pos_id, "user_id": user_id,
                    "symbol": symbol, "side": existing["side"], "qty": existing["qty"],
                    "entry_price": existing["entry_price"], "exit_price": price,
                    "pnl": pnl, "pnl_pct": pnl / (existing["entry_price"] * existing["qty"]) * 100,
                    "exit_time": datetime.now(timezone.utc).isoformat(), "source": source,
                })
                _db()["paper_positions"].update_one(
                    {"id": pos_id}, {"$set": {"status": "closed"}}
                )
                cash = _get_cash(user_id)
                _set_cash(user_id, cash + price * existing["qty"])
                entry["action"] = "closed"
                entry["detail"] = f"PnL ${pnl:.2f}"
        else:
            entry["detail"] = "HOLD — no action" if signal == "HOLD" else (
                "Already long" if signal == "BUY" else "No position to close"
            )

        log.append(entry)

    return jsonify({"bot": source, "dry_run": dry_run, "actions": log})


@paper_bp.route("/account/<user_id>/reset", methods=["POST"])
def reset_account(user_id):
    _db()["paper_positions"].delete_many({"user_id": user_id})
    _db()["paper_trades"].delete_many({"user_id": user_id})
    _set_cash(user_id, STARTING_CASH)
    return jsonify({"reset": True, "cash": STARTING_CASH})
