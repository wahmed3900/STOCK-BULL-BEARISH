import time
import requests
from flask import jsonify

START_TIME = time.time()

@app.route("/api/health", methods=["GET"])
def api_health():
    health = {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "components": {
            "flask_app": True,
            "database": False,
            "ai_model": False,
            "sse_stream": False,
            "external_api": False,
            "env_vars": True
        }
    }

    # 1. Database health
    try:
        db.client.admin.command("ping")
        health["components"]["database"] = True
    except Exception as e:
        health["components"]["database"] = str(e)

    # 2. AI model health
    try:
        test = get_quote("AAPL")
        health["components"]["ai_model"] = test is not None
    except Exception as e:
        health["components"]["ai_model"] = str(e)

    # 3. SSE stream health (simple check)
    try:
        health["components"]["sse_stream"] = True
    except Exception as e:
        health["components"]["sse_stream"] = str(e)

    # 4. External API (Yahoo Finance)
    try:
        r = requests.get("https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL", timeout=3)
        health["components"]["external_api"] = r.status_code == 200
    except Exception as e:
        health["components"]["external_api"] = str(e)

    # 5. Environment variables (Render)
    try:
        import os
        required = ["MONGO_URI"]
        missing = [v for v in required if os.getenv(v) is None]
        health["components"]["env_vars"] = (len(missing) == 0) or missing
    except Exception as e:
        health["components"]["env_vars"] = str(e)

    return jsonify(health), 200
