document.addEventListener("DOMContentLoaded", () => {
  const helpButton = document.getElementById("helpDialogButton");
  const dialog = document.getElementById("simpleDialog");
  const closeButtons = dialog?.querySelectorAll("[data-dialog-close]");

  if (!helpButton || !dialog) {
    return;
  }

  helpButton.addEventListener("click", () => {
    dialog.showModal();
  });

  closeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      dialog.close();
    });
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  // SSE streaming for live sentiment from /sentiment/<symbol>
  const live = document.getElementById("live-stream");
  if (live && live.dataset && live.dataset.symbol) {
    const symbol = live.dataset.symbol;
    const summaryEl = document.getElementById("summary");
    const evt = new EventSource(`/sentiment/${encodeURIComponent(symbol)}`);
    let buffered = "";

    evt.onmessage = (e) => {
      const data = e.data || "";
      if (data === "[DONE]") {
        evt.close();
        live.classList.add("stream-done");
        return;
      }
      if (data.startsWith("[STREAM ERROR]")) {
        live.textContent = data;
        evt.close();
        return;
      }

      // append token to buffer and update UI
      buffered += data;
      if (summaryEl) summaryEl.textContent = buffered;
    };

    evt.onerror = (err) => {
      console.error("SSE error", err);
      evt.close();
    };
  }
});
