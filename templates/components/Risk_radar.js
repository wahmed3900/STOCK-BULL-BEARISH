

function renderRiskRadar(data) {
  new Chart(document.getElementById("riskRadarChart"), {
    type: "radar",
    data: {
      labels: ["Volatility", "Liquidity", "Sector Risk", "Macro Risk", "Momentum"],
      datasets: [{
        label: "Risk Profile",
        data: data,
        backgroundColor: "rgba(99, 102, 241, 0.3)",
        borderColor: "#6366f1"
      }]
    }
  });
}
