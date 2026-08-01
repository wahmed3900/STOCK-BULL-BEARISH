fetch("/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    messages: [
      { role: "user", content: "Analyze AAPL bullish or bearish today." }
    ]
  })
});
