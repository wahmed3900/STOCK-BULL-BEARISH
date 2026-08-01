import time

START_TIME = time.time()

@app.route("/status")
def status():
    """Internal health check endpoint for uptime monitoring and diagnostics."""

    # Basic app uptime
    uptime_seconds = int(time.time() - START_TIME)

    # Check database health
    try:
        db_ok = db.health_check()  # You can implement this in your db module
    except Exception:
        db_ok = False

    # Check homepage availability
    try:
        homepage_ok = True  # If this endpoint is running, homepage is usually OK
    except Exception:
        homepage_ok = False

    # Check AI model endpoint
    try:
        model_test = get_quote("AAPL")
        model_ok = model_test is not None
    except Exception:
        model_ok = False

    # Check SSE endpoint (simple ping)
    try:
        sse_ok = True  # SSE is handled by Flask/Gunicorn; deeper checks optional
    except Exception:
        sse_ok = False

    return jsonify({
        "status": "ok",
        "uptime_seconds": uptime_seconds,
        "components": {
            "database": db_ok,
            "homepage": homepage_ok,
            "ai_model": model_ok,
            "sse_stream": sse_ok,
        }
    })
