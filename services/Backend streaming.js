from flask import Flask, Response, request
from together import Together

app = Flask(__name__)

client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

@app.route("/stream", methods=["POST"])
def stream():
    messages = request.json.get("messages", [])

    def generate():
        stream = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=messages,
            stream=True
        )

        try:
            for chunk in stream:
                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [STREAM ERROR] {str(e)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream")
