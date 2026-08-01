from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/sentiment")
def sentiment():
    symbol = request.args.get("symbol")
    provider = request.args.get("provider", "openrouter")
    return jsonify({"sentiment": f"Sentiment for {symbol} using {provider}"})

@app.route("/premium/analysis")
def premium_analysis():
    symbol = request.args.get("symbol")
    return jsonify({"analysis": f"Advanced analysis for {symbol}"})

if __name__ == "__main__":
    app.run(debug=True)
