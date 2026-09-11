const evtSource = new EventSource(`/pipeline/AAPL`);

evtSource.onmessage = (event) => {
  console.log("token:", event.data);
};
