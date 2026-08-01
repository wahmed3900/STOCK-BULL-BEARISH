const evtSource = new EventSource("/stream");

evtSource.onmessage = (event) => {
  console.log("token:", event.data);
};
