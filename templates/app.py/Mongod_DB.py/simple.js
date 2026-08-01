const evtSource = new EventSource(`/sentiment/AAPL`);

evtSource.onmessage = (event) => {
  console.log("token:", event.data);
};
