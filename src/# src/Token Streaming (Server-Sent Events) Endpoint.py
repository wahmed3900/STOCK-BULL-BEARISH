@app.route("/api/v1/ai/stream", methods=["POST"])
def ai_stream():
    """Streams OpenRouter responses back token-by-token using SSE."""
    if not openrouter_client:
        return jsonify({"error": "AI service unavailable"}), 503

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    chosen_model = data.get("model", app_config.DEFAULT_AI_MODEL)

    if not user_message:
        return jsonify({"error": "Message content required"}), 400

    def generate_tokens():
        try:
            # Setting stream=True breaks response down into generator chunks
            response_stream = openrouter_client.chat.completions.create(
                model=chosen_model,
                messages=[{"role": "user", "content": user_message}],
                stream=True
            )
            for chunk in response_stream:
                token = chunk.choices[0].delta.content
                if token:
                    # SSE protocol format requirement
                    yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate_tokens()), mimetype="text/event-stream")
