function renderSentimentGrid(stocks) {
  const grid = document.getElementById("sentimentGrid");
  grid.innerHTML = "";

  stocks.forEach(s => {
    const card = document.createElement("div");
    card.className = "p-4 bg-slate-700 rounded-lg";
    card.innerHTML = `
      <h4 class="font-semibold">${s.symbol}</h4>
      <p class="text-sm">${s.sentiment}</p>
    `;
    grid.appendChild(card);
  });
}
