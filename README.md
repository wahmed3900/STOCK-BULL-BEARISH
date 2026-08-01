# Bull/Bear Stock Dashboard

A Flask dashboard that tracks stocks and gives an AI-generated bull/bearish
verdict on each one using a free OpenRouter model. Free tier is capped at
3 stocks; Pro (demo-gated, no real payment) unlocks unlimited stocks + AI
analysis.

## Setup

```bash
cd stock-dashboard
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `OPENROUTER_API_KEY` — required for AI analysis. Get a free key at
  https://openrouter.ai/keys (no card needed for free-tier models).
- `ALPHA_VANTAGE_API_KEY` — optional fallback if Yahoo Finance rate-limits
  you. Free key at https://www.alphavantage.co/support/#api-key
  (25 requests/day on the free plan).
- `MONGODB_URI` — defaults to `mongodb://localhost:27017` (local Mongo).
  For a free hosted option, spin up a MongoDB Atlas free tier cluster at
  https://www.mongodb.com/cloud/atlas/register and use the
  `mongodb+srv://...` connection string it gives you.

You'll need MongoDB running before you start the app — either install it
locally (`brew install mongodb-community` on Mac, or the official install
guide for your OS), or use Atlas and skip the local install entirely.

Load the `.env` file before running (or `pip install python-dotenv` and add
`from dotenv import load_dotenv; load_dotenv()` at the top of `app.py`):

```bash
export $(cat .env | xargs)   # macOS/Linux
python app.py
```

Visit http://127.0.0.1:5000

## How it works

- **Price data**: `services/stock_data.py` tries `yfinance` first (free,
  no key required), falls back to Alpha Vantage if that fails.
- **AI sentiment**: `services/sentiment.py` sends the price/change to
  OpenRouter using `meta-llama/llama-3.3-70b-instruct:free`. Swap the
  `MODEL` constant if that model is retired — check
  https://openrouter.ai/models?max_price=0 for current free models.
- **Tiers & watchlist**: stored in MongoDB (`database.py`), in a
  `settings` doc and a `watchlist` collection. Free = 3 stock max, no
  AI button. Pro = unlimited + AI analysis.

## What's stubbed / next steps

- **Payments**: the "Upgrade to Pro" button just flips a flag in the DB —
  no money changes hands. To actually charge $9/mo, wire up
  [Stripe Checkout](https://stripe.com/docs/checkout/quickstart) or
  Stripe Billing and call `db.set_tier("pro")` from your webhook handler
  after a successful payment, not from a button click.
- **Multi-user**: this is single-user (one watchlist, one tier flag).
  Add a `users` table + Flask-Login before deploying for real customers.
- **Deploy**: works the same way as your Railway.app chat app deployment —
  push to GitHub, connect the repo in Railway, set the env vars there.

## Project structure

```
stock-dashboard/
├── app.py                  # Flask routes
├── database.py              # MongoDB persistence
├── services/
│   ├── stock_data.py        # yfinance + Alpha Vantage
│   └── sentiment.py         # OpenRouter AI analysis
├── templates/
│   ├── base.html
│   └── index.html
├── static/style.css
├── requirements.txt
└── .env.example
```
