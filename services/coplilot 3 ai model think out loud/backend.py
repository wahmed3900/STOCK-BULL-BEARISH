@app.route("/pipeline/<symbol>")
def pipeline(symbol):

    def generate():
        yield from stream_reasoning(symbol)
        yield from stream_sentiment(symbol)
        yield from stream_risk(symbol)
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream")
