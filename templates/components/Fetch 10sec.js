async function loadAlerts() {
  const res = await fetch("/premium/alerts");
  const data = await res.json();

  const box = document.getElementById("alertsBox");
  box.innerHTML = "";

  data.alerts.forEach(alert => {
    const div = document.createElement("div");
    div.className = "p-4 bg-slate-700 rounded-lg";
    div.innerHTML = `
      <strong>${alert.symbol}</strong>: ${alert.message}
      <div class="text-xs text-slate-400">${alert.timestamp}</div>
    `;
    box.appendChild(div);
  });
}

setInterval(loadAlerts, 10000);
