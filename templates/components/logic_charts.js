async function loadSentimentTimeline(symbol) {
  const res = await fetch(`/premium/sentiment-timeline?symbol=${symbol}`);
  const data = await res.json();

  const labels = data.timeline.map(t => new Date(t.timestamp).toLocaleTimeString());
  const values = data.timeline.map(t => t.confidence);

  renderSentimentTimeline(labels, values);
}
