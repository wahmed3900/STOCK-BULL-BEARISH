from flask import Response
from together import Together
import os

client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

@app.route("/sentiment/<symbol>")
def sentiment(symbol):

    prompt = f"Analyze {symbol}. Is it bullish or bearish today? Stream the reasoning."

    def generate():
        stream = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )

        try:
            for chunk in stream:
                token = chunk.choices[0].delta.get("content", "")
                yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [STREAM ERROR] {str(e)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream")
