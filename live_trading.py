"""
live_trading.py — Flask Blueprint for Alpaca live trading (Bot 2)
Register in app.py:
    from live_trading import live_bp
    app.register_blueprint(live_bp, url_prefix='/api/live')

Env vars needed:
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER (default "true")
"""

import os
import requests as _requests
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, request, jsonify
from pymongo import MongoClient

live_bp = Blueprint("live", __name__)

ALPACA_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
IS_PAPER      = os.getenv("ALPACA_PAPER", "true").lower() != "false"
BACKEND_URL   = os.getenv("SELF_BASE_URL", "http://localhost:5000")
MONGO_URI     = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME       = os.getenv("MONGO_DB_NAME", "stockai")

ALPACA_BASE = "https://paper-api.alpaca.markets" if IS_PAPER else "https://api.alpaca.markets"
DATA_BASE   = "https://data.alpaca.markets"

_mongo = None

def _db():
    global _mongo
    if _mongo is None:
        _mongo = MongoClient(MONGO_URI)
    return _mongo[DB_NAME]

def _alpaca_headers():
    return {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}

def _alpaca_get(path, params=None):
    r = _requests.get(f"{ALPACA_BASE}/v2/{path}", headers=_alpaca_headers(), params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def _alpaca_post(path, body):
    r = _requests.post(f"{ALPACA_BASE}/v2/{path}", headers=_alpaca_headers(), json=body, timeout=15)
    r.raise_for_status()
    return r.json()

def _alpaca_delete(path):
    r = _requests.delete(f"{ALPACA_BASE}/v2/{path}", headers=_alpaca_headers(), timeout=15)
    return r.status_code

def _get_signal_and_indicators(symbol):
    try:
        r = _requests.get(f"{BACKEND_URL}/api/analyze/{symbol}", timeout=20)
        d = r.json()
        return {
            "ai_signal":   (d.get("recommendation") or d.get("signal") or "HOLD").upper(),
            "price":       float(d.get("price") or d.get("current_price") or 0),
            "rsi":         float(d.get("rsi") or 50),
            "macd":        float(d.get("macd") or 0),
            "macd_signal": float(d.get("macd_signal") or d.get("macd_sig") or 0),
            "atr":         float(d.get("atr") or 1.0),
        }
    except Exception:
        return {"ai_signal": "HOLD", "price": 0, "rsi": 50, "macd": 0, "macd_signal": 0, "atr": 1.0}

def _clean(doc):
    doc = dict(doc)
    doc.pop("_id", None)
    return doc

DEFAULT_CONFIG = {
    "mode": "paper", "watchlist": ["AAPL","TSLA","NVDA","MSFT","SPY"],
    "ai_source": "gemini", "max_positions": 5, "risk_pct": 1.0,
    "daily_loss_limit": 2.0, "rsi_buy_max": 65.0, "rsi_sell_min": 75.0,
    "require_macd": True, "stop_loss_atr": 2.0, "take_profit_atr": 4.0, "enabled": False,
}

# ── Account ───────────────────────────────────────────────────────────────

@live_bp.route("/account")
def get_account():
    try:
        acct = _alpaca_get("account")
        equity     = float(acct.get("equity", 0))
        last_eq    = float(acct.get("last_equity", equity))
        pnl_today  = equity - last_eq
        return jsonify({
            "id":             acct.get("id"),
            "status":         acct.get("status"),
            "mode":           "paper" if IS_PAPER else "live",
            "equity":         equity,
            "cash":           float(acct.get("cash", 0)),
            "buying_power":   float(acct.get("buying_power", 0)),
            "portfolio_value": float(acct.get("portfolio_value", 0)),
            "pnl_today":      pnl_today,
            "pnl_today_pct":  (pnl_today / last_eq * 100) if last_eq else 0,
            "daytrade_count": acct.get("daytrade_count", 0),
            "pattern_day_trader": acct.get("pattern_day_trader", False),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@live_bp.route("/positions")
def get_positions():
    try:
        positions = _alpaca_get("positions")
        return jsonify([{
            "symbol":            p.get("symbol"),
            "qty":               float(p.get("qty", 0)),
            "side":              p.get("side"),
            "entry_price":       float(p.get("avg_entry_price", 0)),
            "current_price":     float(p.get("current_price", 0)),
            "market_value":      float(p.get("market_value", 0)),
            "unrealized_pnl":    float(p.get("unrealized_pl", 0)),
            "unrealized_pnl_pct": float(p.get("unrealized_plpc", 0)) * 100,
            "cost_basis":        float(p.get("cost_basis", 0)),
        } for p in positions])
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@live_bp.route("/orders")
def get_orders():
    try:
        limit  = request.args.get("limit", 50)
        status = request.args.get("status", "all")
        orders = _alpaca_get("orders", {"status": status, "limit": limit})
        return jsonify([{
            "id":               o.get("id"),
            "symbol":           o.get("symbol"),
            "side":             o.get("side"),
            "type":             o.get("type"),
            "qty":              float(o.get("qty") or 0),
            "filled_qty":       float(o.get("filled_qty") or 0),
            "status":           o.get("status"),
            "filled_avg_price": float(o["filled_avg_price"]) if o.get("filled_avg_price") else None,
            "created_at":       o.get("created_at"),
            "filled_at":        o.get("filled_at"),
        } for o in orders])
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@live_bp.route("/order", methods=["POST"])
def place_order():
    data    = request.json
    dry_run = data.get("dry_run", True)
    symbol  = data.get("symbol", "").upper()
    qty     = float(data.get("qty", 1))
    side    = data.get("side", "buy")

    if dry_run:
        return jsonify({"dry_run": True, "preview": data})

    body = {"symbol": symbol, "qty": qty, "side": side, "type": "market", "time_in_force": "day"}
    if data.get("stop_loss"):
        body["stop_loss"] = {"stop_price": str(data["stop_loss"])}
    if data.get("take_profit"):
        body["take_profit"] = {"limit_price": str(data["take_profit"])}

    try:
        order = _alpaca_post("orders", body)
        return jsonify({"order_id": order.get("id"), "symbol": order.get("symbol"),
                        "status": order.get("status")})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@live_bp.route("/order/<order_id>", methods=["DELETE"])
def cancel_order(order_id):
    _alpaca_delete(f"orders/{order_id}")
    return jsonify({"cancelled": order_id})


@live_bp.route("/orders/all", methods=["DELETE"])
def cancel_all():
    _alpaca_delete("orders")
    return jsonify({"cancelled": "all"})


# ── Bot 2 config ──────────────────────────────────────────────────────────

@live_bp.route("/bot2/config/<user_id>")
def get_bot2_config(user_id):
    doc = _db()["bot2_config"].find_one({"user_id": user_id})
    if not doc:
        cfg = {**DEFAULT_CONFIG, "user_id": user_id}
        _db()["bot2_config"].insert_one(cfg)
        return jsonify(_clean(cfg))
    return jsonify(_clean(doc))


@live_bp.route("/bot2/config/<user_id>", methods=["PUT"])
def save_bot2_config(user_id):
    data = request.json
    data["user_id"] = user_id
    _db()["bot2_config"].update_one({"user_id": user_id}, {"$set": data}, upsert=True)
    return jsonify(data)


# ── Bot 2 run ─────────────────────────────────────────────────────────────

@live_bp.route("/bot2/run/<user_id>", methods=["POST"])
def run_bot2(user_id):
    dry_run = request.args.get("dry_run", "true").lower() != "false"
    cfg_doc = _db()["bot2_config"].find_one({"user_id": user_id}) or {**DEFAULT_CONFIG, "user_id": user_id}
    cfg     = {**DEFAULT_CONFIG, **cfg_doc}

    log    = []
    errors = []

    try:
        acct      = _alpaca_get("account")
        equity    = float(acct.get("equity", 0))
        last_eq   = float(acct.get("last_equity", equity))
        pnl_today = equity - last_eq
        daily_limit = -(equity * cfg["daily_loss_limit"] / 100)

        if pnl_today < daily_limit:
            return jsonify({"halted": True, "reason": f"Daily loss limit hit (${pnl_today:.2f}). Bot halted."})

        open_positions = {p["symbol"]: p for p in _alpaca_get("positions")}
        open_count     = len(open_positions)
    except Exception as e:
        return jsonify({"error": f"Alpaca error: {e}"}), 502

    for symbol in cfg.get("watchlist", []):
        symbol = symbol.upper()
        entry  = {"symbol": symbol, "action": "none", "reason": "", "detail": ""}
        data   = _get_signal_and_indicators(symbol)

        ai_signal    = data["ai_signal"]
        rsi          = data["rsi"]
        macd         = data["macd"]
        macd_sig     = data["macd_signal"]
        atr          = data["atr"]
        price        = data["price"]
        macd_bullish = macd > macd_sig

        entry["ai_signal"]    = ai_signal
        entry["rsi"]          = round(rsi, 1)
        entry["macd_bullish"] = macd_bullish

        already_long = symbol in open_positions

        # EXIT
        if already_long:
            should_exit = False
            reason      = ""
            if ai_signal == "SELL":
                should_exit = True
                reason = "AI SELL signal"
            elif rsi > cfg["rsi_sell_min"]:
                should_exit = True
                reason = f"RSI overbought ({rsi:.1f})"

            if should_exit:
                entry["action"] = "would_close" if dry_run else "closed"
                entry["reason"] = reason
                if not dry_run:
                    try:
                        pos = open_positions[symbol]
                        body = {"symbol": symbol, "qty": abs(float(pos["qty"])),
                                "side": "sell", "type": "market", "time_in_force": "day"}
                        order = _alpaca_post("orders", body)
                        entry["detail"] = f"Order {order.get('id')} submitted"
                    except Exception as e:
                        entry["action"] = "error"
                        errors.append(f"{symbol} close: {e}")
            else:
                entry["action"] = "hold"
                entry["reason"] = "Holding"
            log.append(entry)
            continue

        # ENTRY
        if ai_signal != "BUY":
            entry["action"] = "skip"
            entry["reason"] = f"Signal is {ai_signal}"
            log.append(entry)
            continue
        if open_count >= cfg["max_positions"]:
            entry["action"] = "skip"
            entry["reason"] = f"Max positions ({cfg['max_positions']}) reached"
            log.append(entry)
            continue
        if rsi > cfg["rsi_buy_max"]:
            entry["action"] = "skip"
            entry["reason"] = f"RSI too high ({rsi:.1f})"
            log.append(entry)
            continue
        if cfg["require_macd"] and not macd_bullish:
            entry["action"] = "skip"
            entry["reason"] = f"MACD not bullish"
            log.append(entry)
            continue
        if price <= 0 or atr <= 0:
            entry["action"] = "skip"
            entry["reason"] = "Invalid price/ATR"
            log.append(entry)
            continue

        stop_distance = atr * cfg["stop_loss_atr"]
        risk_dollars  = equity * (cfg["risk_pct"] / 100)
        qty           = max(1, round(risk_dollars / stop_distance))
        stop_price    = round(price - stop_distance, 2)
        target_price  = round(price + atr * cfg["take_profit_atr"], 2)

        entry.update({"qty": qty, "price": price, "stop_loss": stop_price,
                      "take_profit": target_price, "risk_dollars": round(risk_dollars, 2)})

        if dry_run:
            entry["action"] = "would_buy"
            entry["reason"] = "All criteria passed"
            entry["detail"] = f"Would buy {qty} @ ~${price:.2f} | SL ${stop_price} | TP ${target_price}"
        else:
            try:
                body = {
                    "symbol": symbol, "qty": qty, "side": "buy",
                    "type": "market", "time_in_force": "day",
                    "stop_loss": {"stop_price": str(stop_price)},
                    "take_profit": {"limit_price": str(target_price)},
                }
                order = _alpaca_post("orders", body)
                open_count += 1
                entry["action"] = "bought"
                entry["reason"] = "All criteria passed"
                entry["detail"] = f"Order {order.get('id')} | SL ${stop_price} | TP ${target_price}"
            except Exception as e:
                entry["action"] = "error"
                entry["reason"] = str(e)
                errors.append(f"{symbol}: {e}")

        log.append(entry)

    run = {"id": str(uuid4()), "user_id": user_id, "run_time": datetime.now(timezone.utc).isoformat(),
           "mode": cfg["mode"], "actions": log, "errors": errors, "dry_run": dry_run}
    _db()["bot2_runs"].insert_one(run)

    return jsonify({"dry_run": dry_run, "mode": cfg["mode"], "equity": equity,
                    "pnl_today": round(pnl_today, 2), "open_positions": open_count,
                    "actions": log, "errors": errors, "run_id": run["id"]})


@live_bp.route("/bot2/runs/<user_id>")
def get_bot2_runs(user_id):
    limit = int(request.args.get("limit", 20))
    docs  = list(_db()["bot2_runs"].find({"user_id": user_id}).sort("run_time", -1).limit(limit))
    return jsonify([_clean(d) for d in docs])


@live_bp.route("/bot2/liquidate/<user_id>", methods=["POST"])
def liquidate_all(user_id):
    try:
        _alpaca_delete("orders")
        positions = _alpaca_get("positions")
        closed = 0
        for p in positions:
            _alpaca_post("orders", {"symbol": p["symbol"], "qty": abs(float(p["qty"])),
                                    "side": "sell", "type": "market", "time_in_force": "day"})
            closed += 1
        return jsonify({"orders_cancelled": "all", "positions_closed": closed,
                        "timestamp": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 502
