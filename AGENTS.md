# stock-dashboard Agent Instructions

## Purpose
This repository is a Flask-based stock dashboard with AI-generated bull/bear sentiment and a separate HyperFrames promo-video project under `promo-video/`.

## What AI agents should know first
- The main app is Python/Flask with MongoDB persistence and an AI sentiment service.
- The repo also contains a `promo-video/` HyperFrames composition with its own `AGENTS.md` and should be treated as a separate project area.
- Root-level `README.md` describes the dashboard and setup, but the source layout is not fully aligned with that doc.

## Key files and folders
- `README.md` — repo overview, setup, and architecture notes.
- `requirements.txt` — Python dependencies used by the dashboard backend.
- `package.json` — Node/Tailwind deps for static tooling.
- `database.py` — MongoDB persistence for the watchlist and tier settings.
- `services/stock_data.py` — stock quote retrieval via `yfinance` and optional Alpha Vantage fallback.
- `services/sentiment.py` — OpenRouter-based AI sentiment analysis.
- `services/services/endpoint.py` — current Flask server entrypoint for the backend streaming API.
- `templates/` — HTML templates used by the dashboard UI.
- `static/` — CSS and frontend assets.
- `promo-video/AGENTS.md` — separate instructions for the HyperFrames composition in `promo-video/`.

## Current conventions and important notes
- Use `requirements.txt` for Python package installs and `package.json` for Node/Tailwind tooling.
- The current backend app is in `services/services/endpoint.py`; `app.py` at the repository root is not the runtime Flask entrypoint.
- `services/flask.py` and `services/__init__.py` are currently empty placeholders; verify before editing or assuming they are active.
- Environment variables are required from `.env.example`:
  - `OPENROUTER_API_KEY` — enables AI stock sentiment.
  - `ALPHA_VANTAGE_API_KEY` — optional fallback for stock quotes.
  - `MONGODB_URI` — MongoDB connection string.
  - `TOGETHER_API_KEY` — used by the streaming endpoint in `services/services/endpoint.py`.
- The repo includes both Python and JavaScript/TypeScript files, so use language-appropriate tools and inspect file-level imports.

## When modifying the app
- For AI sentiment changes, inspect `services/sentiment.py` and `services/stock_data.py`.
- For persistence changes, work in `database.py`.
- For UI changes, edit `templates/` and `static/` assets.
- For backend request routing or streaming, edit `services/services/endpoint.py`.

## What not to do unless asked
- Do not modify `promo-video/` unless the task is explicitly about the video composition or graphics.
- Do not assume the root `app.py` is the active Flask app.

## Useful commands
- `pip install -r requirements.txt`
- `python3 services/services/endpoint.py`
- `python3 -m pip install --upgrade pip` if dependency installation fails.

## Why this file exists
This file helps AI coding agents avoid stale assumptions from the repo root and focus on the actual service entrypoints, env vars, and the separate promo-video project.
