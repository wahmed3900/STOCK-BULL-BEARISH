from flask import Blueprint, Response, request
import os

# `together` is optional for local tests; fall back if missing so the module can import
try:
    from together import Together
except Exception:
    Together = None

bp = Blueprint("services_endpoint", __name__)

client = None
if Together is not None:
    try:
        client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
    except Exception:
        # Gracefully fall back when the Together client cannot initialize
        # (for example when the TOGETHER_API_KEY is not set).
        client = None


@bp.route("/stream", methods=["POST"])
def stream():
    data = request.json
    messages = data.get("messages", [])

    def generate():
        # Lazy initialize the Together client when the endpoint is called.
        global client
        if client is None and Together is not None:
            try:
                client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
            except Exception:
                client = None

        if client is None:
            yield "data: [STREAM ERROR] together package not installed\n\n"
            yield "data: [DONE]\n\n"
            return

        stream = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=messages,
            stream=True,
        )

        try:
            for chunk in stream:
                token = chunk.choices[0].delta.get("content", "")
                yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [STREAM ERROR] {str(e)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream")

