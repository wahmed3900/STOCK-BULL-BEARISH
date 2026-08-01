@app.route("/api/model", methods=["GET"])
def api_model():
    import os
    import time

    result = {
        "status": "ok",
        "model_loaded": False,
        "model_name": None,
        "env_vars": True,
        "test_inference": False,
        "latency_ms": None,
        "error": None
    }

    start = time.time()

    try:
        # 1. Check environment variables
        required_env = ["TOGETHER_API_KEY", "OPENAI_API_KEY"]
        missing = [v for v in required_env if os.getenv(v) is None]

        if missing:
            result["env_vars"] = missing  # list of missing vars

        # 2. Check model object exists
        if "model" in globals() and model is not None:
            result["model_loaded"] = True
            result["model_name"] = getattr(model, "name", "unknown")
        else:
            raise Exception("Model object not loaded in memory")

        # 3. Run a tiny test inference
        try:
            test = get_quote("AAPL")
            if test is not None:
                result["test_inference"] = True
        except Exception as e:
            result["test_inference"] = str(e)

        # 4. Latency
        result["latency_ms"] = int((time.time() - start) * 1000)

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return jsonify(result), 200
