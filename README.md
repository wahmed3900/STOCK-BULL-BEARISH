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

## Deploy (Render / Heroku / Google Cloud)

Quick notes to deploy this app to Render, Heroku, or Google Cloud.

- Ensure required environment variables are set before deploy:
  - `OPENROUTER_API_KEY` — enables AI sentiment. You can also store this in Google Secret Manager as `openrouter-api-key`.
  - `ALPHA_VANTAGE_API_KEY` — optional fallback for quotes. You can also store this in Google Secret Manager as `alpha-vantage-key`.
  - `MONGODB_URI` and `MONGODB_DB_NAME` — production MongoDB (Atlas recommended)
  - `TOGETHER_API_KEY` — if you use together.ai streaming endpoints
  - `SECRET_KEY` — Flask secret for sessions
  - `GOOGLE_CLOUD_PROJECT` — required if you want the app to load secrets from Google Secret Manager

### Google Secret Manager

If you are deploying to Google Cloud or want secret-backed config:

```bash
pip install google-cloud-secret-manager
```

Create secrets in Google Secret Manager with these names:
- `openrouter-api-key`
- `alpha-vantage-key`

Then set:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

The app will first check environment variables and then fall back to Google Secret Manager automatically.

### Render quick deploy

1. Create a new Web Service in Render and link the GitHub repo.
2. Set the Environment to `Python`, and in the "Start Command" use the Procfile or set:

```
gunicorn src.app:app --log-file -
```

3. Add environment variables in the Render dashboard (same names as above).

### Google Cloud Run quick deploy

1. Build and deploy the app with Cloud Run or App Engine.
2. Set the same environment variables in Cloud Run.
3. Grant the service account access to Secret Manager:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:YOUR_SERVICE_ACCOUNT \
  --role=roles/secretmanager.secretAccessor
```

4. Set `GOOGLE_CLOUD_PROJECT` so the app can resolve secrets automatically.

- A `Procfile` is included and uses Gunicorn to run the app in production:

```
web: gunicorn src.app:app --log-file -
```

- Heroku quick deploy

```
heroku create my-stock-dashboard
heroku config:set OPENROUTER_API_KEY=… MONGODB_URI=… MONGODB_DB_NAME=stock_dashboard SECRET_KEY=…
git push heroku main
```

- Render quick deploy

1. Create a new Web Service in Render and link the GitHub repo.
2. Set the Environment to `Python`, and in the "Start Command" use the Procfile or set:

```
gunicorn src.app:app --log-file -
```

3. Add environment variables in the Render dashboard (same names as above).

- Local production-like start

```
pip install -r requirements.txt
PORT=5001 gunicorn src.app:app --log-file -
```

Notes:
- The app will fall back to an in-memory default tier if MongoDB is unavailable, but for production you should provide a managed MongoDB (Atlas) and set `MONGODB_URI`.
- If you rely on real-time streaming (`/stream` or `/sentiment`), ensure `TOGETHER_API_KEY` is configured in the environment.

Docker (local)

Use Docker Compose to run a local MongoDB and the app for development/testing:

```
docker-compose build
docker-compose up
```

This maps container port `5000` to host `5001` so the app is available at `http://localhost:5001` and Mongo is available at `mongodb://localhost:27017`.

Differences between tasks we added:

- `requirements.txt` (`together`): installs the Together.ai SDK so server-side streaming uses real model tokens instead of the fallback error.
- `runtime.txt`: pins the Python runtime used by hosting providers (Heroku/Render) to avoid runtime mismatches.
- `Dockerfile` + `docker-compose.yml`: provide a reproducible local environment (app + Mongo) for development and integration testing; useful when you don't want to rely on external managed services during development.


