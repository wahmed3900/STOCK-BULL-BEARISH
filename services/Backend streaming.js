import express from "express";
import Together from "together-ai";

const app = express();
app.use(express.json());

const together = new Together({
  apiKey: process.env.TOGETHER_API_KEY
});

app.post("/stream", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const { messages } = req.body;

  const stream = await together.chat.completions.create({
    model: "meta-llama/Meta-Llama-3.1-70B-Instruct",
    messages,
    stream: true
  });

  try {
    for await (const chunk of stream) {
      const token = chunk?.choices?.[0]?.delta?.content || "";
      res.write(`data: ${token}\n\n`);
    }
  } catch (err) {
    res.write(`data: [STREAM ERROR] ${err.message}\n\n`);
  }

  res.write("data: [DONE]\n\n");
  res.end();
});

app.listen(3000, () => console.log("Streaming backend running on port 3000"));
