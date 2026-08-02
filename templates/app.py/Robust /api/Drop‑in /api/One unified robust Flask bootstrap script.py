from flask import Flask, jsonify, Response, send_from_directory
import time

app = Flask(__name__, static_folder="static")

START_TIME = time.time()

# -----------------------------
# HEALTH ENDPOINT
# -----------------------------
@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "ok",
        "uptime": int(time.time() - START_TIME),
        "message": "backend healthy"
    }), 200

# -----------------------------
# MODEL ENDPOINT
# -----------------------------
@app.route("/api/model", methods=["GET"])
def api_model():
    return jsonify({
        "model": "ready",
        "status": "ok"
    }), 200

# -----------------------------
# SSE STREAM ENDPOINT
# -----------------------------
@app.route("/stream/<symbol>")
def stream(symbol):
    def event_stream():
        yield f"data: streaming {symbol}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

# -----------------------------
# STATIC TAILWIND CSS
# -----------------------------
@app.route("/static/css/tailwind.css")
def tailwind_css():
    return send_from_directory("static/css", "tailwind.css")

# -----------------------------
# HOME
# -----------------------------
@app.route("/")
def home():
    return "STOCK-BULL-BEARISH backend running", 200
