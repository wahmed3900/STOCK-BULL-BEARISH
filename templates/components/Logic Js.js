function updateConfidenceMeter(value) {
  document.getElementById("confidenceBar").style.width = value + "%";
  document.getElementById("confidenceText").innerText = `Confidence: ${value}%`;
}
