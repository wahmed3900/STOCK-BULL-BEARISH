@app.route("/sentiment/<symbol>")
def sentiment(symbol):
    # old non-streaming logic
