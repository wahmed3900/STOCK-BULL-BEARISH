@app.route("/")
def index():
  pub_key = os.getenv("STRIPE_PUBLISHABLE_KEY")
  return render_template("index.html", publishable_key=pub_key)
