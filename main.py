# ============================================================
# main.py — StockAI API Engine (FastAPI, all-in-one)
# Auth, refresh tokens, blacklist, email verify, password reset,
# rate limit, admin, P/E evaluator, news, AI summaries, Stripe
# webhook, subscription gating, alerts engine, watchlist,
# portfolio, search, discovery.
# ============================================================

# ---------- IMPORTS ----------
import os
import math
import uuid
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
import numpy as np
import stripe
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from bson import ObjectId
from fastapi import (
    FastAPI, APIRouter, Depends, HTTPException, Query, Request, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr, validator
from pymongo import MongoClient

load_dotenv()
logger = logging.getLogger("stock_api")
logging.basicConfig(level=logging.INFO)

# ============================================================
# CONFIG
# ============================================================
MONGODB_URI        = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME    = os.getenv("MONGODB_DB_NAME", "stock_dashboard")
JWT_SECRET         = os.getenv("JWT_SECRET")
JWT_ALGORITHM      = "HS256"
ACCESS_TOKEN_MIN   = 30
REFRESH_TOKEN_DAYS = 30
EMAIL_VERIFY_HOURS = 48
STRIPE_SECRET_KEY  = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL       = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_WORKSPACE_ID = os.getenv("ANTHROPIC_WORKSPACE_ID")  # only needed for keys not scoped to a workspace
CLAUDE_MODEL       = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
AI_SUMMARY_TTL_S   = int(os.getenv("AI_SUMMARY_TTL_S", "600"))  # frontend polls every 60s; don't pay for 2 AI calls each time
AI_ORDER           = [p.strip().lower() for p in os.getenv("AI_ORDER", "gemini,claude").split(",") if p.strip()]  # first = primary, next = fallback
AI_FAIL_COOLDOWN_S = int(os.getenv("AI_FAIL_COOLDOWN_S", "300"))  # skip a failing provider for 5 min
AI_ENABLED         = os.getenv("AI_ENABLED", "true").lower() not in ("false", "0", "no", "off")  # false = free rule-based summaries only

SMTP_HOST    = os.getenv("SMTP_HOST")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER")
SMTP_PASS    = os.getenv("SMTP_PASS")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://stock-dashboard-frontend-one.vercel.app")

RATE_LIMIT_REQUESTS  = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_S  = int(os.getenv("RATE_LIMIT_WINDOW_S", "60"))
ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))

VALID_PERIODS   = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}

DISCLAIMER = (
    "For educational and informational purposes only. Not investment, financial or trading advice. "
    "Market data may be delayed or inaccurate. AI-generated summaries can be wrong."
)

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ---------- OPTIONAL AI CLIENTS ----------
# Uses the current google-genai SDK (google.generativeai is end-of-life).
gemini_client = None
if GEMINI_API_KEY and AI_ENABLED:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

claude_client = None
if ANTHROPIC_API_KEY and AI_ENABLED:
    try:
        import anthropic
        headers = {"anthropic-workspace-id": ANTHROPIC_WORKSPACE_ID} if ANTHROPIC_WORKSPACE_ID else None
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, default_headers=headers)
    except Exception as e:
        logger.warning(f"Anthropic init failed: {e}")

# ============================================================
# JSON SAFETY — NaN / Infinity / numpy scalars -> valid JSON
# ============================================================
def clean_json(obj):
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    """Turns NaN/Infinity into null so responses are always valid JSON."""
    def render(self, content) -> bytes:
        return super().render(clean_json(content))

# ============================================================
# FASTAPI APP + CORS
# ============================================================
app = FastAPI(
    default_response_class=SafeJSONResponse,
    title="StockAI API Engine",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DATABASE
# ============================================================
class Database:
    def __init__(self):
        try:
            self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.db              = self.client[MONGODB_DB_NAME]
            self.users           = self.db["users"]
            self.watchlists      = self.db["watchlists"]
            self.portfolio       = self.db["portfolio"]
            self.alerts          = self.db["alerts"]
            self.transactions    = self.db["transactions"]
            self.subscriptions   = self.db["subscriptions"]
            self.blacklist       = self.db["token_blacklist"]
            self.email_verif     = self.db["email_verifications"]
            self.password_resets = self.db["password_resets"]
            self.is_connected    = True
            self._ensure_indexes()
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            self.is_connected = False
            for name in ("users", "watchlists", "portfolio", "alerts",
                         "transactions", "subscriptions", "blacklist",
                         "email_verif", "password_resets"):
                setattr(self, name, None)

    def _ensure_indexes(self):
        try:
            self.users.create_index("email", unique=True)
            self.blacklist.create_index("expires_at", expireAfterSeconds=0)
            self.email_verif.create_index("token", unique=True)
            self.password_resets.create_index("token", unique=True)
            self.alerts.create_index([("user_id", 1), ("symbol", 1)])
            self.watchlists.create_index([("user_id", 1), ("symbol", 1)], unique=True)
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

db = Database()

def require_db():
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")

# ============================================================
# PYDANTIC CLASSES
# ============================================================
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class WatchlistItem(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)

    @validator("symbol")
    def upper_symbol(cls, v: str) -> str:
        return v.upper().strip()


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PortfolioItem(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)
    transaction_type: TransactionType
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)

    @validator("symbol")
    def upper_symbol(cls, v: str) -> str:
        return v.upper().strip()


class AlertCondition(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"


class AlertItem(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)
    target_price: float = Field(..., gt=0)
    condition: AlertCondition

    @validator("symbol")
    def upper_symbol(cls, v: str) -> str:
        return v.upper().strip()


class CheckoutRequest(BaseModel):
    plan_id: str
    success_url: str
    cancel_url: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    role: str = "user"
    email_verified: bool = False
    subscription_tier: str = "free"
    created_at: Optional[datetime] = None


class Sector(str, Enum):
    tech_growth      = "tech_growth"
    bank             = "bank"
    utility          = "utility"
    mature_industry  = "mature_industry"
    healthcare       = "healthcare"
    consumer_staples = "consumer_staples"
    energy           = "energy"
    general          = "general"


class GrowthProfile(str, Enum):
    fast     = "fast"
    moderate = "moderate"
    slow     = "slow"
    risky    = "risky"


class PEQuery(BaseModel):
    pe: float = Field(..., gt=0)
    sector: Sector = Sector.general
    growth: GrowthProfile = GrowthProfile.moderate
    risk_free_rate: Optional[float] = None


class PEVerdict(BaseModel):
    pe: float
    earnings_yield_pct: float
    sector: str
    sector_benchmark: dict
    verdict: str
    reasons: List[str]
    market_context: Optional[str] = None
    disclaimer: str = DISCLAIMER


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str

# ============================================================
# RATE LIMITER (per instance; fine for a single Cloud Run instance)
# ============================================================
_rate_store: Dict[str, deque] = defaultdict(deque)

def rate_limit(request: Request):
    # Behind Cloud Run the real client IP is in X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for", "")
    client_ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    now = datetime.utcnow().timestamp()
    window_start = now - RATE_LIMIT_WINDOW_S
    bucket = _rate_store[client_ip]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {RATE_LIMIT_REQUESTS} req / {RATE_LIMIT_WINDOW_S}s",
        )
    bucket.append(now)

# ============================================================
# AUTH HELPERS
# ============================================================
security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def _base_payload(user_id: str, email: str, role: str, token_type: str, ver: int) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "email": email,
        "role": role,
        "type": token_type,
        "ver": ver,  # must match users.token_version, so logout-all / password reset revoke old tokens
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
    }

def generate_access_token(user_id: str, email: str, role: str = "user", ver: int = 0) -> str:
    payload = _base_payload(user_id, email, role, "access", ver)
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_MIN)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def generate_refresh_token(user_id: str, email: str, role: str = "user", ver: int = 0) -> str:
    payload = _base_payload(user_id, email, role, "refresh", ver)
    payload["exp"] = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def issue_tokens(user: Dict[str, Any]) -> Dict[str, str]:
    uid = str(user["_id"])
    role = user.get("role", "user")
    ver = user.get("token_version", 0)
    return {
        "access_token": generate_access_token(uid, user["email"], role, ver),
        "refresh_token": generate_refresh_token(uid, user["email"], role, ver),
        "token_type": "bearer",
    }

def _is_blacklisted(jti: str) -> bool:
    if not db.is_connected:
        return False
    return db.blacklist.find_one({"jti": jti}) is not None

def _decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if data.get("type") != expected_type:
        raise HTTPException(status_code=401, detail=f"Expected {expected_type} token")
    if _is_blacklisted(data.get("jti", "")):
        raise HTTPException(status_code=401, detail="Token revoked")
    return data

def _check_token_version(data: Dict[str, Any], user: Dict[str, Any]):
    if data.get("ver", 0) != user.get("token_version", 0):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    require_db()
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")
    data = _decode_token(credentials.credentials, expected_type="access")
    user = db.users.find_one({"email": data["email"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    _check_token_version(data, user)
    user["_id"] = str(user["_id"])
    return user

async def require_admin(user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

TIER_RANK = {"free": 0, "basic": 1, "pro": 2, "premium": 3}

def _user_tier(user: Dict[str, Any]) -> str:
    return user.get("subscription_tier", "free")

def require_tier(min_tier: str):
    async def _dep(user: Dict[str, Any] = Depends(get_current_user)):
        if TIER_RANK.get(_user_tier(user), 0) < TIER_RANK.get(min_tier, 0):
            raise HTTPException(
                status_code=402,
                detail=f"Requires '{min_tier}' subscription or higher",
            )
        return user
    return _dep

# ============================================================
# EMAIL HELPERS
# ============================================================
def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_HOST:
        logger.info(f"[EMAIL STUB] to={to} subject={subject}")  # don't log bodies: they contain tokens
        return True
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, [to], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False

def create_email_verification(user_id: str, email: str) -> str:
    token = uuid.uuid4().hex
    db.email_verif.insert_one({
        "token": token,
        "user_id": user_id,
        "email": email,
        "expires_at": datetime.utcnow() + timedelta(hours=EMAIL_VERIFY_HOURS),
        "created_at": datetime.utcnow(),
    })
    link = f"{APP_BASE_URL}/api/auth/verify-email?token={token}"
    send_email(email, "Verify your StockAI email", f"Click to verify: {link}")
    return token

def create_password_reset(email: str) -> Optional[str]:
    user = db.users.find_one({"email": email})
    if not user:
        return None
    token = uuid.uuid4().hex
    db.password_resets.insert_one({
        "token": token,
        "user_id": str(user["_id"]),
        "email": email,
        "expires_at": datetime.utcnow() + timedelta(hours=1),
        "created_at": datetime.utcnow(),
    })
    link = f"{FRONTEND_URL}/reset?token={token}"
    send_email(email, "Reset your StockAI password", f"Reset your password: {link}")
    return token

# ============================================================
# TECHNICAL INDICATORS
# ============================================================
def calculate_rsi(data: List[float], period: int = 14) -> Optional[float]:
    s = pd.Series(data).dropna()
    if len(s) <= period:
        return None  # not enough history; frontend shows "—"
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    if avg_loss.iloc[-1] == 0:
        return 100.0
    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
    return float(100 - (100 / (1 + rs)))

def calculate_macd(data: List[float]):
    s = pd.Series(data).dropna()
    if len(s) < 35:  # 26 for the slow EMA + 9 for the signal line
        return 0.0, 0.0, 0.0
    macd_line   = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return (float(macd_line.iloc[-1]),
            float(signal_line.iloc[-1]),
            float(macd_line.iloc[-1] - signal_line.iloc[-1]))

def calculate_bollinger_bands(data: List[float], period: int = 20):
    s = pd.Series(data).dropna()
    if len(s) < period:
        last = float(s.iloc[-1])
        return last, last, last
    mid = s.rolling(period).mean().iloc[-1]
    std = s.rolling(period).std().iloc[-1]
    return float(mid + 2 * std), float(mid), float(mid - 2 * std)

def _check_period(period: str, interval: str = "1d"):
    if period not in VALID_PERIODS:
        raise HTTPException(400, f"Invalid period '{period}'. Use one of: {', '.join(sorted(VALID_PERIODS))}")
    if interval not in VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval '{interval}'")

def safe_history(symbol: str, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
    except Exception as e:
        logger.warning(f"yfinance error for {symbol}: {e}")
        raise HTTPException(status_code=502, detail=f"Couldn't fetch data for {symbol} right now")
    if df is None or df.empty or df["Close"].dropna().empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    return df

def df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    df = df.reset_index()
    df.columns = [str(c) for c in df.columns]
    first = df.columns[0]
    df[first] = pd.to_datetime(df[first]).dt.strftime("%Y-%m-%d")
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict(orient="records")

# ============================================================
# P/E EVALUATOR LOGIC
# ============================================================
SECTOR_BENCHMARKS = {
    Sector.tech_growth:      {"low": 30, "high": 50, "label": "Tech / Growth"},
    Sector.bank:             {"low": 8,  "high": 15, "label": "Bank"},
    Sector.utility:          {"low": 8,  "high": 15, "label": "Utility"},
    Sector.mature_industry:  {"low": 8,  "high": 15, "label": "Mature Industry"},
    Sector.healthcare:       {"low": 15, "high": 25, "label": "Healthcare"},
    Sector.consumer_staples: {"low": 15, "high": 22, "label": "Consumer Staples"},
    Sector.energy:           {"low": 8,  "high": 18, "label": "Energy"},
    Sector.general:          {"low": 15, "high": 20, "label": "Broad Market"},
}
MARKET_AVERAGE_LOW = 15
MARKET_AVERAGE_HIGH = 20


def evaluate_pe(query: PEQuery) -> PEVerdict:
    pe = query.pe
    bench = SECTOR_BENCHMARKS[query.sector]
    low, high = bench["low"], bench["high"]
    reasons: List[str] = []

    # Verdicts describe the P/E relative to typical ranges — not whether to buy.
    if pe < low:
        verdict = "below typical range"
        reasons.append(f"P/E {pe} is below the typical {bench['label']} range ({low}-{high}).")
    elif pe > high:
        verdict = "above typical range"
        reasons.append(f"P/E {pe} is above the typical {bench['label']} range ({low}-{high}).")
    else:
        verdict = "within typical range"
        reasons.append(f"P/E {pe} is within the typical {bench['label']} range ({low}-{high}).")

    if query.growth == GrowthProfile.fast:
        if verdict == "above typical range" and pe <= high * 1.5:
            verdict = "within typical range"
            reasons.append("Fast-growing companies often carry higher P/Es (30-50+).")
    elif query.growth == GrowthProfile.moderate:
        reasons.append("Stable, moderate-growth companies often trade at a P/E near 20.")
    elif query.growth == GrowthProfile.slow:
        if verdict == "within typical range" and pe > 15:
            verdict = "above typical range"
            reasons.append("Slow-growing companies rarely trade above the mid-teens for long.")
    elif query.growth == GrowthProfile.risky:
        if pe > 20:
            verdict = "above typical range"
            reasons.append("Speculative companies with a premium P/E carry extra risk if growth disappoints.")

    if pe < MARKET_AVERAGE_LOW:
        market_context = f"Below the historical US market average band ({MARKET_AVERAGE_LOW}-{MARKET_AVERAGE_HIGH})."
    elif pe > MARKET_AVERAGE_HIGH:
        market_context = f"Above the historical US market average band ({MARKET_AVERAGE_LOW}-{MARKET_AVERAGE_HIGH})."
    else:
        market_context = f"In line with the historical US market average band ({MARKET_AVERAGE_LOW}-{MARKET_AVERAGE_HIGH})."

    if query.risk_free_rate is not None:
        if query.risk_free_rate >= 5 and pe > 20:
            reasons.append("High risk-free rates tend to put pressure on high P/Es.")
        elif query.risk_free_rate <= 2 and pe > 20:
            reasons.append("Low rates tend to support higher P/Es by making future earnings more valuable.")

    return PEVerdict(
        pe=pe,
        earnings_yield_pct=round(100.0 / pe, 2),
        sector=bench["label"],
        sector_benchmark={"low": low, "high": high},
        verdict=verdict,
        reasons=reasons,
        market_context=market_context,
    )

# ============================================================
# AI SUMMARIES (Gemini + Claude)
# ============================================================
_SUMMARY_CACHE: Dict[str, Dict[str, Any]] = {}

def _n(v: Any, digits: int = 2) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "n/a"
    return f"{f:.{digits}f}" if math.isfinite(f) else "n/a"

def _build_prompt(ticker: str, m: Dict[str, Any]) -> str:
    macd = m.get("macd") or {}
    boll = m.get("bollinger") or {}
    return (
        f"Write a neutral, 2-sentence technical snapshot of {ticker.upper()} for a market dashboard.\n"
        f"Data: last close {_n(m.get('latest_close'), 4)}, RSI(14) {_n(m.get('rsi'), 1)}, "
        f"MACD line {_n(macd.get('macd'), 4)}, signal {_n(macd.get('signal'), 4)}, "
        f"histogram {_n(macd.get('histogram'), 4)}, Bollinger upper {_n(boll.get('upper'), 4)}, "
        f"middle {_n(boll.get('middle'), 4)}, lower {_n(boll.get('lower'), 4)}.\n"
        "Describe what the indicators show (for example overbought or oversold conditions, "
        "momentum direction, and where price sits within its bands). Values marked n/a are unavailable; "
        "skip them. Do not give buy, sell or hold recommendations, price targets, or predictions, and "
        "do not tell the reader what to do. Plain English, no headings, no disclaimers."
    )

def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None

def rule_based_summary(ticker: str, m: Dict[str, Any]) -> str:
    """Free, no-AI technical snapshot built straight from the indicator values.
    Descriptive only: no buy/sell/hold language."""
    t = ticker.upper()
    parts: List[str] = []

    rsi = _num(m.get("rsi"))
    if rsi is not None:
        if rsi >= 70:
            parts.append(f"RSI is {rsi:.0f}, in overbought territory, meaning recent gains have been strong relative to losses")
        elif rsi <= 30:
            parts.append(f"RSI is {rsi:.0f}, in oversold territory, meaning recent losses have outweighed gains")
        elif rsi >= 55:
            parts.append(f"RSI is {rsi:.0f}, leaning toward positive momentum without being overbought")
        elif rsi <= 45:
            parts.append(f"RSI is {rsi:.0f}, leaning toward weaker momentum without being oversold")
        else:
            parts.append(f"RSI is {rsi:.0f}, a neutral reading")

    macd = m.get("macd") or {}
    line, sig, hist = _num(macd.get("macd")), _num(macd.get("signal")), _num(macd.get("histogram"))
    if None not in (line, sig, hist) and not (line == 0 and sig == 0 and hist == 0):
        if hist > 0:
            parts.append("the MACD line is above its signal line, showing upward momentum")
        elif hist < 0:
            parts.append("the MACD line is below its signal line, showing downward momentum")
        else:
            parts.append("the MACD line is sitting on its signal line")

    boll = m.get("bollinger") or {}
    close = _num(m.get("latest_close"))
    upper, lower = _num(boll.get("upper")), _num(boll.get("lower"))
    if None not in (close, upper, lower) and upper > lower:
        pos = (close - lower) / (upper - lower)
        if pos > 1:
            parts.append("price has pushed above its upper Bollinger Band, an unusually strong move for this period")
        elif pos < 0:
            parts.append("price has dropped below its lower Bollinger Band, an unusually weak move for this period")
        elif pos >= 0.8:
            parts.append("price is trading near the top of its Bollinger Bands")
        elif pos <= 0.2:
            parts.append("price is trading near the bottom of its Bollinger Bands")
        else:
            parts.append("price is in the middle of its Bollinger Bands")

    if not parts:
        return f"Not enough price history yet to describe {t}'s technicals."
    first = parts[0][0].upper() + parts[0][1:]
    body = "; ".join([first] + parts[1:])
    return f"{t}: {body}. This is an automated reading of the indicators, not a forecast."

def _ask_gemini(prompt: str) -> str:
    if not gemini_client:
        return ""
    resp = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (resp.text or "").strip()

def _ask_claude(prompt: str) -> str:
    if not claude_client:
        return ""
    blocks = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    ).content
    return "".join(b.text for b in blocks if hasattr(b, "text")).strip()

_AI_PROVIDERS = {"gemini": _ask_gemini, "claude": _ask_claude}
_PROVIDER_DOWN_UNTIL: Dict[str, float] = {}

def _provider_ready(name: str) -> bool:
    return datetime.utcnow().timestamp() >= _PROVIDER_DOWN_UNTIL.get(name, 0)

def _mark_provider_down(name: str):
    # After a failure (out of credits, bad key, outage) skip this provider for a
    # while instead of retrying it on every request.
    _PROVIDER_DOWN_UNTIL[name] = datetime.utcnow().timestamp() + AI_FAIL_COOLDOWN_S

def generate_dual_summary(ticker: str, metrics: Dict[str, Any]) -> Dict[str, str]:
    """Returns {gemini, claude, rules}. Fallback chain: AI_ORDER providers one at a
    time (default Gemini, then Claude), then the free rule-based text. 'rules' is
    always filled, so the dashboard shows something even with AI off or out of
    credits. The frontend uses the first non-'Unavailable' value."""
    rules = rule_based_summary(ticker, metrics)
    if not (gemini_client or claude_client):
        return {"gemini": "Unavailable", "claude": "Unavailable", "rules": rules}

    key = f"{ticker.upper()}:{_n(metrics.get('latest_close'), 4)}"
    cached = _SUMMARY_CACHE.get(key)
    now = datetime.utcnow().timestamp()
    if cached and now - cached["ts"] < AI_SUMMARY_TTL_S:
        return {**cached["value"], "rules": rules}

    prompt = _build_prompt(ticker, metrics)

    # Fallback chain: try providers in AI_ORDER, stop at the first that answers.
    # Only ONE paid call per summary; the next provider is only used if the first fails.
    value = {"gemini": "Unavailable", "claude": "Unavailable"}
    for name in AI_ORDER:
        call = _AI_PROVIDERS.get(name)
        if not call or not _provider_ready(name):
            continue
        try:
            text = call(prompt)
        except Exception as e:
            _mark_provider_down(name)
            logger.warning(f"{name.capitalize()} summary failed, trying next provider: {e}")
            continue
        if text:
            value[name] = text
            break

    if any(v != "Unavailable" for v in value.values()):
        _SUMMARY_CACHE[key] = {"ts": now, "value": value}
        if len(_SUMMARY_CACHE) > 500:  # keep memory bounded
            oldest = min(_SUMMARY_CACHE, key=lambda k: _SUMMARY_CACHE[k]["ts"])
            _SUMMARY_CACHE.pop(oldest, None)
    return {**value, "rules": rules}

# ============================================================
# PUBLIC — CORE
# ============================================================
@app.get("/")
def root():
    return {"message": "StockAI API Engine v2.1", "docs": "/docs"}

@app.get("/api/health")
def health():
    return {"status": "ok", "mongodb": db.is_connected, "ai_enabled": AI_ENABLED,
            "gemini": gemini_client is not None, "claude": claude_client is not None,
            "ai_order": AI_ORDER, "rules_fallback": True, "summary_cache_s": AI_SUMMARY_TTL_S,
            "providers_cooling_down": [p for p in AI_ORDER if not _provider_ready(p)]}

@app.get("/api/db-status")
def db_status():
    return {"mongodb": db.is_connected, "database": MONGODB_DB_NAME}

@app.get("/api/stock/{symbol}")
def get_stock(symbol: str, period: str = "3mo"):
    symbol = symbol.upper().strip()
    _check_period(period)
    hist = safe_history(symbol, period=period)
    close = hist["Close"].dropna().tolist()
    macd, signal, hist_val = calculate_macd(close)
    upper, mid, lower = calculate_bollinger_bands(close)
    metrics = {
        "latest_close": float(close[-1]),
        "rsi": calculate_rsi(close),
        "macd": {"macd": macd, "signal": signal, "histogram": hist_val},
        "bollinger": {"upper": upper, "middle": mid, "lower": lower},
    }
    return {
        "symbol": symbol,
        "metrics": metrics,
        "history": df_to_records(hist),
        "summary": generate_dual_summary(symbol, metrics),
        "source": "Yahoo Finance (may be delayed)",
        "disclaimer": DISCLAIMER,
    }

@app.get("/api/chart/hybrid")
def chart_hybrid(symbol: str, period: str = "6mo", interval: str = "1d"):
    symbol = symbol.upper().strip()
    _check_period(period, interval)
    df = safe_history(symbol, period=period, interval=interval)
    close = df["Close"].dropna().tolist()
    upper, mid, lower = calculate_bollinger_bands(close)
    macd, signal, hist_val = calculate_macd(close)
    return {
        "symbol": symbol,
        "candles": df_to_records(df),
        "overlays": {
            "bollinger": {"upper": upper, "middle": mid, "lower": lower},
            "macd": {"macd": macd, "signal": signal, "histogram": hist_val},
            "rsi": calculate_rsi(close),
        },
    }

@app.get("/api/market/historical")
def market_historical(symbol: str, start: str, end: str, interval: str = "1d"):
    symbol = symbol.upper().strip()
    if interval not in VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval '{interval}'")
    try:
        df = yf.Ticker(symbol).history(start=start, end=end, interval=interval)
    except Exception as e:
        logger.warning(f"yfinance historical error for {symbol}: {e}")
        raise HTTPException(status_code=502, detail="Fetch failed")
    if df.empty:
        raise HTTPException(status_code=404, detail="No data in range")
    return {"symbol": symbol, "start": start, "end": end, "records": df_to_records(df)}

# ============================================================
# SEARCH / DISCOVERY — same 7 asset classes as the frontend
# ============================================================
ASSET_CLASSES = {
    "stocks":      ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"],
    "etfs":        ["SPY", "QQQ", "VTI", "IWM", "DIA", "VOO"],
    "indices":     ["^GSPC", "^DJI", "^IXIC", "^RUT"],
    "forex":       ["EURUSD=X", "GBPUSD=X", "JPY=X", "AUDUSD=X"],
    "crypto":      ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"],
    "commodities": ["GC=F", "SI=F", "CL=F", "NG=F"],
    "bonds":       ["^TNX", "^TYX", "^FVX", "^IRX"],
}

@app.get("/api/asset-classes")
def asset_classes():
    return {
        "asset_classes": list(ASSET_CLASSES.keys()),
        "counts": {k: len(v) for k, v in ASSET_CLASSES.items()},
    }

@app.get("/api/search")
def search(q: str, limit: int = Query(10, ge=1, le=50)):
    q_upper = q.upper()
    hits = []
    for cls, symbols in ASSET_CLASSES.items():
        for s in symbols:
            if q_upper in s:
                hits.append({"symbol": s, "asset_class": cls})
    return {"query": q, "results": hits[:limit]}

@app.get("/api/search/autocomplete")
def autocomplete(q: str, limit: int = Query(8, ge=1, le=50)):
    return {"suggestions": [r["symbol"] for r in search(q, limit)["results"]]}

@app.get("/api/search/popular")
def popular(limit: int = Query(10, ge=1, le=50)):
    flat = [s for syms in ASSET_CLASSES.values() for s in syms]
    return {"popular": flat[:limit]}

@app.get("/api/multi-asset/{symbol}")
def multi_asset(symbol: str):
    symbol = symbol.upper().strip()
    cls = next((c for c, syms in ASSET_CLASSES.items() if symbol in syms), "unknown")
    df = safe_history(symbol, period="1mo")
    close = df["Close"].dropna()
    first = float(close.iloc[0])
    return {
        "symbol": symbol,
        "asset_class": cls,
        "latest_close": float(close.iloc[-1]),
        "change_pct_1mo": float((close.iloc[-1] / first - 1) * 100) if first else None,
    }

@app.post("/api/social/share")
def social_share(payload: Dict[str, Any]):
    symbol = str(payload.get("symbol", "")).upper().strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    return {
        "share_url": f"{FRONTEND_URL}/?symbol={symbol}",
        "text": f"Check out the technicals for {symbol} on StockAI",
    }

# ============================================================
# P/E EVALUATOR ROUTES
# ============================================================
@app.post("/api/pe/evaluate", response_model=PEVerdict)
def pe_evaluate(query: PEQuery):
    return evaluate_pe(query)

@app.get("/api/pe/benchmarks")
def pe_benchmarks():
    return {s.value: d for s, d in SECTOR_BENCHMARKS.items()}

@app.get("/api/pe/market-average")
def pe_market_average():
    return {"low": MARKET_AVERAGE_LOW, "high": MARKET_AVERAGE_HIGH}

# ============================================================
# NEWS ROUTER (inlined)
# ============================================================
news_router = APIRouter(prefix="/api/news", tags=["news"])
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_TTL = 300


def _fetch_news(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        raw = yf.Ticker(symbol).news or []
    except Exception as e:
        logger.warning(f"News fetch failed for {symbol}: {e}")
        raise HTTPException(status_code=502, detail="News fetch failed")
    out = []
    for item in raw[:limit]:
        content = item.get("content", item)
        out.append({
            "title":     content.get("title"),
            "publisher": (content.get("provider") or {}).get("displayName")
                         or item.get("publisher"),
            "link":      (content.get("clickThroughUrl") or {}).get("url")
                         or item.get("link"),
            "published": content.get("pubDate") or item.get("providerPublishTime"),
            "summary":   content.get("summary"),
            "type":      item.get("type", "STORY"),
        })
    return out


@news_router.get("/{symbol}")
def get_news(symbol: str, limit: int = Query(10, ge=1, le=50)):
    symbol = symbol.upper().strip()
    now = datetime.utcnow().timestamp()
    cache_key = f"{symbol}:{limit}"
    cached = _NEWS_CACHE.get(cache_key)
    if cached and now - cached["ts"] < _NEWS_TTL:
        return {"symbol": symbol, "cached": True, "articles": cached["articles"]}
    articles = _fetch_news(symbol, limit=limit)
    _NEWS_CACHE[cache_key] = {"ts": now, "articles": articles}
    return {"symbol": symbol, "cached": False, "articles": articles}


@news_router.get("/{symbol}/headlines")
def get_headlines(symbol: str, limit: int = Query(5, ge=1, le=20)):
    symbol = symbol.upper().strip()
    articles = _fetch_news(symbol, limit=limit)
    return {"symbol": symbol, "headlines": [a["title"] for a in articles]}


app.include_router(news_router)

# ============================================================
# STRIPE
# ============================================================
PLANS = [
    # Lineup: Free -> Starter $99 -> Premium $199. The old $9 "basic" plan is no
    # longer sold (TIER_RANK still knows it, so any existing basic subscriber keeps access).
    # Starter keeps id/tier "pro" so require_tier("pro") gating keeps working.
    {"id": "pro",     "name": "StockAI Starter", "price": 9900,  "currency": "usd",
     "interval": "month", "tier": "pro"},
    {"id": "premium", "name": "StockAI Premium", "price": 19900, "currency": "usd",
     "interval": "month", "tier": "premium"},
]

def _allowed_redirect(url: str) -> bool:
    # Only send users back to your own sites after checkout
    allowed = [FRONTEND_URL, APP_BASE_URL] + [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]
    return any(url.startswith(a.rstrip("/")) for a in allowed if a)

@app.get("/api/plans")
def plans():
    return {"plans": PLANS}

@app.post("/api/create-checkout-session")
def create_checkout_session(req: CheckoutRequest,
                            user: Dict[str, Any] = Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe not configured")
    plan = next((p for p in PLANS if p["id"] == req.plan_id), None)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if not (_allowed_redirect(req.success_url) and _allowed_redirect(req.cancel_url)):
        raise HTTPException(400, "success_url and cancel_url must point to this site")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": plan["currency"],
                    "unit_amount": plan["price"],
                    "recurring": {"interval": plan["interval"]},
                    "product_data": {"name": plan["name"]},
                },
                "quantity": 1,
            }],
            customer_email=user["email"],
            metadata={"user_id": user["_id"], "tier": plan["tier"]},
            subscription_data={"metadata": {"user_id": user["_id"], "tier": plan["tier"]}},
            success_url=req.success_url,
            cancel_url=req.cancel_url,
        )
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(502, "Couldn't start checkout, please try again")
    return {"checkout_url": session.url, "session_id": session.id}

def _set_user_tier(user_id: Optional[str], tier: str):
    if not user_id:
        return
    try:
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"subscription_tier": tier}})
    except Exception as e:
        logger.warning(f"Tier update failed for {user_id}: {e}")

@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook secret not configured")
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    require_db()
    etype = event["type"]
    data  = event["data"]["object"]

    if etype == "checkout.session.completed":
        meta = data.get("metadata") or {}
        user_id = meta.get("user_id")
        tier    = meta.get("tier", "basic")
        if user_id:
            db.subscriptions.update_one(
                {"user_id": user_id},
                {"$set": {
                    "user_id": user_id,
                    "tier": tier,
                    "status": "active",
                    "stripe_customer_id": data.get("customer"),
                    "stripe_subscription_id": data.get("subscription"),
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True,
            )
            _set_user_tier(user_id, tier)

    elif etype == "customer.subscription.updated":
        # Covers failed payments / past_due / unpaid, not just cancellations
        sub = db.subscriptions.find_one({"stripe_subscription_id": data.get("id")})
        if sub:
            stripe_status = data.get("status")
            db.subscriptions.update_one(
                {"_id": sub["_id"]},
                {"$set": {"status": stripe_status, "updated_at": datetime.utcnow()}},
            )
            if stripe_status in ("active", "trialing"):
                _set_user_tier(sub["user_id"], sub.get("tier", "basic"))
            elif stripe_status in ("unpaid", "canceled", "incomplete_expired"):
                _set_user_tier(sub["user_id"], "free")

    elif etype == "customer.subscription.deleted":
        sub = db.subscriptions.find_one({"stripe_subscription_id": data.get("id")})
        if sub:
            db.subscriptions.update_one(
                {"_id": sub["_id"]},
                {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}},
            )
            _set_user_tier(sub["user_id"], "free")

    return {"received": True}

@app.get("/success")
def success():
    return {"status": "success", "message": "Subscription activated."}

@app.get("/cancel")
def cancel():
    return {"status": "cancelled", "message": "Checkout cancelled."}

# ============================================================
# USERS
# ============================================================
def _new_user_doc(email: str, password: str) -> Dict[str, Any]:
    return {
        "email": email,
        "password": hash_password(password),
        "role": "user",
        "email_verified": False,
        "subscription_tier": "free",
        "token_version": 0,
        "created_at": datetime.utcnow(),
    }

@app.post("/api/users", response_model=UserResponse, status_code=201,
          dependencies=[Depends(rate_limit)])
def create_user(user: UserRegister):
    require_db()
    if db.users.find_one({"email": user.email}):
        raise HTTPException(400, "Email already registered")
    doc = _new_user_doc(user.email, user.password)
    result = db.users.insert_one(doc)
    create_email_verification(str(result.inserted_id), user.email)
    return UserResponse(
        id=str(result.inserted_id),
        email=user.email,
        role=doc["role"],
        email_verified=False,
        subscription_tier="free",
        created_at=doc["created_at"],
    )

@app.get("/api/users/{email}", response_model=UserResponse)
def get_user(email: str, _admin: Dict[str, Any] = Depends(require_admin)):
    require_db()
    user = db.users.find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        role=user.get("role", "user"),
        email_verified=user.get("email_verified", False),
        subscription_tier=user.get("subscription_tier", "free"),
        created_at=user.get("created_at"),
    )

# ============================================================
# AUTH
# ============================================================
@app.post("/api/auth/register", status_code=201,
          dependencies=[Depends(rate_limit)])
def register(user: UserRegister):
    require_db()
    if db.users.find_one({"email": user.email}):
        raise HTTPException(400, "Email already registered")
    doc = _new_user_doc(user.email, user.password)
    result = db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    uid = str(result.inserted_id)
    create_email_verification(uid, user.email)
    return {
        **issue_tokens(doc),
        "user": {"id": uid, "email": user.email, "role": "user",
                 "email_verified": False, "subscription_tier": "free"},
    }

@app.post("/api/auth/login", dependencies=[Depends(rate_limit)])
def login(user: UserLogin):
    require_db()
    db_user = db.users.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(401, "Invalid credentials")
    return {
        **issue_tokens(db_user),
        "user": {
            "id": str(db_user["_id"]),
            "email": db_user["email"],
            "role": db_user.get("role", "user"),
            "email_verified": db_user.get("email_verified", False),
            "subscription_tier": db_user.get("subscription_tier", "free"),
        },
    }

@app.post("/api/auth/refresh", dependencies=[Depends(rate_limit)])
def refresh_token(req: RefreshTokenRequest):
    require_db()
    data = _decode_token(req.refresh_token, expected_type="refresh")
    try:
        user = db.users.find_one({"_id": ObjectId(data["user_id"])})
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "User not found")
    _check_token_version(data, user)
    # Rotate: the old refresh token can't be reused
    db.blacklist.insert_one({
        "jti": data["jti"],
        "expires_at": datetime.utcfromtimestamp(data["exp"]),
    })
    return issue_tokens(user)

@app.get("/api/auth/me", response_model=UserResponse)
def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return UserResponse(
        id=current_user["_id"],
        email=current_user["email"],
        role=current_user.get("role", "user"),
        email_verified=current_user.get("email_verified", False),
        subscription_tier=current_user.get("subscription_tier", "free"),
        created_at=current_user.get("created_at"),
    )

@app.post("/api/auth/logout")
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if credentials and db.is_connected:
        try:
            data = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            db.blacklist.insert_one({
                "jti": data["jti"],
                "expires_at": datetime.utcfromtimestamp(data["exp"]),
            })
        except Exception as e:
            logger.warning(f"Logout blacklist warning: {e}")
    return {"status": "logged out", "user_id": current_user["_id"]}

@app.post("/api/auth/logout-all")
def logout_all(current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    db.users.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$inc": {"token_version": 1}},
    )
    return {"status": "all tokens invalidated"}

# ============================================================
# EMAIL VERIFICATION
# ============================================================
@app.post("/api/auth/verify-email")
def verify_email(req: VerifyEmailRequest):
    require_db()
    row = db.email_verif.find_one({"token": req.token})
    if not row:
        raise HTTPException(400, "Invalid or used token")
    if row.get("expires_at") and row["expires_at"] < datetime.utcnow():
        db.email_verif.delete_one({"token": req.token})
        raise HTTPException(400, "Verification link expired, please request a new one")
    db.users.update_one(
        {"_id": ObjectId(row["user_id"])},
        {"$set": {"email_verified": True}},
    )
    db.email_verif.delete_one({"token": req.token})
    return {"status": "verified", "email": row["email"]}

@app.get("/api/auth/verify-email")
def verify_email_get(token: str):
    return verify_email(VerifyEmailRequest(token=token))

@app.post("/api/auth/resend-verification", dependencies=[Depends(rate_limit)])
def resend_verification(current_user: Dict[str, Any] = Depends(get_current_user)):
    if current_user.get("email_verified"):
        return {"status": "already verified"}
    create_email_verification(current_user["_id"], current_user["email"])
    return {"status": "sent"}

# ============================================================
# PASSWORD RESET
# ============================================================
@app.post("/api/auth/forgot-password", dependencies=[Depends(rate_limit)])
def forgot_password(req: PasswordResetRequest):
    require_db()
    create_password_reset(req.email)
    return {"status": "if email exists, reset link sent"}

@app.post("/api/auth/reset-password", dependencies=[Depends(rate_limit)])
def reset_password(req: PasswordResetConfirm):
    require_db()
    row = db.password_resets.find_one({"token": req.token})
    if not row:
        raise HTTPException(400, "Invalid reset token")
    if row.get("expires_at") and row["expires_at"] < datetime.utcnow():
        db.password_resets.delete_one({"token": req.token})
        raise HTTPException(400, "Reset token expired")
    new_hash = hash_password(req.new_password)
    db.users.update_one(
        {"_id": ObjectId(row["user_id"])},
        {"$set": {"password": new_hash},
         "$inc": {"token_version": 1}},  # signs out every existing session
    )
    db.password_resets.delete_one({"token": req.token})
    return {"status": "password updated"}

# ============================================================
# WATCHLIST
# ============================================================
@app.post("/api/watchlist", status_code=201)
def add_watchlist(item: WatchlistItem,
                  current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    if db.watchlists.find_one({"user_id": current_user["_id"], "symbol": item.symbol}):
        raise HTTPException(409, "Already in watchlist")
    db.watchlists.insert_one({
        "user_id": current_user["_id"],
        "symbol": item.symbol,
        "added_at": datetime.utcnow(),
    })
    return {"status": "added", "symbol": item.symbol}

@app.get("/api/watchlist")
def get_watchlist(current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    docs = list(db.watchlists.find({"user_id": current_user["_id"]}))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"watchlist": docs}

@app.delete("/api/watchlist/{symbol}")
def delete_watchlist(symbol: str,
                     current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    result = db.watchlists.delete_one({
        "user_id": current_user["_id"], "symbol": symbol.upper(),
    })
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted", "symbol": symbol.upper()}

# ============================================================
# PORTFOLIO
# ============================================================
@app.post("/api/portfolio", status_code=201)
def add_portfolio(tx: PortfolioItem,
                  current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    uid = current_user["_id"]
    holding = db.portfolio.find_one({"user_id": uid, "symbol": tx.symbol})

    # Validate a SELL before recording anything
    if tx.transaction_type == TransactionType.SELL and (not holding or holding["quantity"] < tx.quantity):
        raise HTTPException(400, "Insufficient holdings")

    db.transactions.insert_one({
        "user_id": uid, "symbol": tx.symbol,
        "transaction_type": tx.transaction_type.value,
        "quantity": tx.quantity, "price": tx.price,
        "timestamp": datetime.utcnow(),
    })

    if tx.transaction_type == TransactionType.BUY:
        if holding:
            new_qty = holding["quantity"] + tx.quantity
            new_avg = ((holding["quantity"] * holding["average_buy_price"]) +
                       (tx.quantity * tx.price)) / new_qty
            db.portfolio.update_one(
                {"_id": holding["_id"]},
                {"$set": {"quantity": new_qty,
                          "average_buy_price": new_avg,
                          "updated_at": datetime.utcnow()}},
            )
        else:
            db.portfolio.insert_one({
                "user_id": uid, "symbol": tx.symbol,
                "quantity": tx.quantity,
                "average_buy_price": tx.price,
                "updated_at": datetime.utcnow(),
            })
    else:
        new_qty = holding["quantity"] - tx.quantity
        if new_qty <= 1e-9:
            db.portfolio.delete_one({"_id": holding["_id"]})
        else:
            db.portfolio.update_one(
                {"_id": holding["_id"]},
                {"$set": {"quantity": new_qty, "updated_at": datetime.utcnow()}},
            )
    return {"status": "success"}

@app.get("/api/portfolio")
def get_portfolio(current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    docs = list(db.portfolio.find({"user_id": current_user["_id"]}))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"portfolio": docs}

@app.delete("/api/portfolio/{symbol}")
def delete_portfolio(symbol: str,
                     current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    result = db.portfolio.delete_one({
        "user_id": current_user["_id"], "symbol": symbol.upper(),
    })
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted", "symbol": symbol.upper()}

# ============================================================
# ALERTS
# ============================================================
@app.post("/api/alerts", status_code=201)
def create_alert(alert: AlertItem,
                 current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    doc = {
        "user_id": current_user["_id"],
        "symbol": alert.symbol,
        "target_price": alert.target_price,
        "condition": alert.condition.value,
        "created_at": datetime.utcnow(),
        "active": True,
        "triggered": False,
        "triggered_at": None,
    }
    result = db.alerts.insert_one(doc)
    return {"status": "created", "alert_id": str(result.inserted_id)}

@app.get("/api/alerts")
def get_alerts(current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    docs = list(db.alerts.find({"user_id": current_user["_id"]}))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"alerts": docs}

@app.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: str,
                 current_user: Dict[str, Any] = Depends(get_current_user)):
    require_db()
    try:
        oid = ObjectId(alert_id)
    except Exception:
        raise HTTPException(400, "Invalid alert id")
    result = db.alerts.delete_one({"_id": oid, "user_id": current_user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Alert not found")
    return {"status": "deleted", "alert_id": alert_id}

# ============================================================
# ALERT TRIGGERING ENGINE
# ============================================================
def _check_alerts_once():
    """Blocking work (MongoDB + yfinance). Runs in a worker thread so it
    never freezes the web server's event loop."""
    if not db.is_connected:
        return
    alerts = list(db.alerts.find({"active": True, "triggered": False}))
    prices: Dict[str, Optional[float]] = {}  # one fetch per symbol, not per alert
    for alert in alerts:
        symbol = alert["symbol"]
        if symbol not in prices:
            try:
                df = yf.Ticker(symbol).history(period="1d", interval="1m")
                closes = df["Close"].dropna() if not df.empty else None
                prices[symbol] = float(closes.iloc[-1]) if closes is not None and len(closes) else None
            except Exception as e:
                logger.warning(f"Alert price fetch failed for {symbol}: {e}")
                prices[symbol] = None
        price = prices[symbol]
        if price is None:
            continue

        target = alert["target_price"]
        cond   = alert["condition"]
        hit = (cond == "ABOVE" and price >= target) or \
              (cond == "BELOW" and price <= target)
        if not hit:
            continue

        db.alerts.update_one(
            {"_id": alert["_id"]},
            {"$set": {
                "triggered": True,
                "active": False,
                "triggered_at": datetime.utcnow(),
                "triggered_price": price,
            }},
        )
        try:
            user = db.users.find_one({"_id": ObjectId(alert["user_id"])})
        except Exception:
            user = None
        if user:
            direction = "above" if cond == "ABOVE" else "below"
            send_email(
                user["email"],
                f"StockAI alert: {symbol} is {direction} {target}",
                f"{symbol} is now {price:.4g}, {direction} your alert level of {target}.\n\n{DISCLAIMER}",
            )
        logger.info(f"Alert fired: {symbol} {cond} {target} @ {price}")

async def alert_checker_loop():
    while True:
        try:
            await asyncio.to_thread(_check_alerts_once)
        except Exception as e:
            logger.exception(f"Alert checker error: {e}")
        await asyncio.sleep(ALERT_CHECK_INTERVAL)

@app.on_event("startup")
async def start_background_tasks():
    app.state.alert_task = asyncio.create_task(alert_checker_loop())
    logger.info("Alert checker started")

# ============================================================
# ADMIN
# ============================================================
@app.get("/api/admin/users")
def admin_list_users(_admin: Dict[str, Any] = Depends(require_admin),
                     limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0)):
    require_db()
    docs = list(db.users.find({}, {"password": 0}).skip(skip).limit(limit))
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"users": docs, "count": len(docs)}

@app.post("/api/admin/users/{email}/promote")
def admin_promote(email: str, _admin: Dict[str, Any] = Depends(require_admin)):
    require_db()
    result = db.users.update_one(
        {"email": email}, {"$set": {"role": "admin"}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"status": "promoted", "email": email}

@app.post("/api/admin/users/{email}/demote")
def admin_demote(email: str, _admin: Dict[str, Any] = Depends(require_admin)):
    require_db()
    result = db.users.update_one(
        {"email": email}, {"$set": {"role": "user"}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"status": "demoted", "email": email}

@app.get("/api/admin/stats")
def admin_stats(_admin: Dict[str, Any] = Depends(require_admin)):
    require_db()
    return {
        "users":         db.users.count_documents({}),
        "subscriptions": db.subscriptions.count_documents({"status": "active"}),
        "alerts":        db.alerts.count_documents({}),
        "portfolio":     db.portfolio.count_documents({}),
        "watchlists":    db.watchlists.count_documents({}),
    }

# ============================================================
# PREMIUM-ONLY (tier-gated)
# ============================================================
@app.get("/api/premium/ai-summary/{symbol}")
def premium_ai_summary(symbol: str,
                       user: Dict[str, Any] = Depends(require_tier("pro"))):
    symbol = symbol.upper().strip()
    hist = safe_history(symbol, period="3mo")
    close = hist["Close"].dropna().tolist()
    macd, signal, hist_val = calculate_macd(close)
    upper, mid, lower = calculate_bollinger_bands(close)
    metrics = {
        "latest_close": float(close[-1]),
        "rsi": calculate_rsi(close),
        "macd": {"macd": macd, "signal": signal, "histogram": hist_val},
        "bollinger": {"upper": upper, "middle": mid, "lower": lower},
    }
    return {"symbol": symbol, "metrics": metrics,
            "summary": generate_dual_summary(symbol, metrics),
            "disclaimer": DISCLAIMER}

@app.get("/api/premium/deep-analysis/{symbol}")
def premium_deep_analysis(symbol: str,
                          user: Dict[str, Any] = Depends(require_tier("premium"))):
    symbol = symbol.upper().strip()
    hist = safe_history(symbol, period="6mo")
    close = hist["Close"].dropna().tolist()
    macd, signal, hist_val = calculate_macd(close)
    upper, mid, lower = calculate_bollinger_bands(close)
    return {
        "symbol": symbol,
        "rsi": calculate_rsi(close),
        "macd": {"macd": macd, "signal": signal, "histogram": hist_val},
        "bollinger": {"upper": upper, "middle": mid, "lower": lower},
        "history_points": len(close),
        "note": "Premium-only deep analysis",
        "disclaimer": DISCLAIMER,
    }

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
