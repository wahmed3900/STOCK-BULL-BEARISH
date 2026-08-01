let selectedModel = "openrouter/free";

document.getElementById("modelSelector").addEventListener("change", (e) => {
  selectedModel = e.target.value;
  console.log("Model selected:", selectedModel);
});
