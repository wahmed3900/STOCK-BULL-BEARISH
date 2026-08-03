from flask import Blueprint, Response
import os

# `together` is optional for local tests; fall back if missing so the module can import
try:
    from together import Together
except Exception:
    Together = None

bp = Blueprint("streaming", __name__)

client = None
if Together is not None:
    try:
        client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
    except Exception:
        # If the Together client fails to initialize (e.g. missing API key),
        # leave `client` as None so imports and local testing continue.
        client = None


@bp.route("/sentiment/<symbol>")
def sentiment(symbol):

    prompt = f"Analyze {symbol}. Is it bullish or bearish today? Stream the reasoning."

    def generate():
        # Lazily initialize the Together client at request time so missing
        # environment variables or transient errors don't break module import.
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
            messages=[{"role": "user", "content": prompt}],
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


@bp.route("/stream/<symbol>")
def stream_sentiment(symbol):
    return sentiment(symbol)
