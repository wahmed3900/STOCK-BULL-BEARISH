function renderHeatmap(data) {
  const heatmap = document.getElementById("heatmap");
  heatmap.innerHTML = "";

  data.forEach(val => {
    const cell = document.createElement("div");
    cell.className = "h-10 rounded";
    cell.style.backgroundColor = val > 0 ? "#10b981" : "#ef4444";
    heatmap.appendChild(cell);
  });
}
