document.getElementById("sentimentBtn").addEventListener("click", async () => {
  const symbol = document.getElementById("symbolInput").value;

  await runSentiment(symbol);
  loadSentimentTimeline(symbol);
});
