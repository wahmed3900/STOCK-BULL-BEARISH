document.getElementById("addWatchlistBtn").addEventListener("click", async () => {
  const symbol = document.getElementById("watchlistInput").value;

  const res = await fetch("/premium/watchlist", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({symbol})
  });

  const data = await res.json();
  alert(data.message);
});
