function renderSentimentTimeline(labels, values) {
  new Chart(document.getElementById("sentimentTimelineChart"), {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: "AI Confidence Over Time",
        data: values,
        borderColor: "#10b981",
        backgroundColor: "rgba(16, 185, 129, 0.2)",
        tension: 0.4
      }]
    },
    options: {
      scales: {
        y: { beginAtZero: true, max: 100 }
      }
    }
  });
}
