@app.route("/api/v1/ai/chat", methods=["POST"])
@limiter.limit("10 per minute")  # Protects your balance from endpoint abuse
def ai_chat():
    """Process prompt inquiries using OpenRouter models."""
    if not openrouter_client:
        return jsonify({"error": "AI service is unconfigured or unavailable"}), 503

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    chosen_model = data.get("model", app_config.DEFAULT_AI_MODEL)

    if not user_message:
        return jsonify({"error": "Message body parameter is required"}), 400

    log = logger.bind(model=chosen_model, message_length=len(user_message))

    try:
        start_time = time.time()
        response = openrouter_client.chat.completions.create(
            model=chosen_model,
            messages=[{"role": "user", "content": user_message}]
        )
        
        ai_response = response.choices[0].message.content
        duration = time.time() - start_time
        
        log.info("openrouter_request_success", duration_seconds=round(duration, 3))
        return jsonify({
            "status": "success",
            "model_used": chosen_model,
            "response": ai_response,
            "timestamp": utc_iso()
        })

    except Exception as e:
        log.error("openrouter_request_failed", error=str(e))
        return jsonify({"error": f"Failed to retrieve AI response: {str(e)}"}), 500
