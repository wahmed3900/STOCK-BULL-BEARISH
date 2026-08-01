import { analyzeStock } from "@/services/ai";

export default async function handler(req, res) {
  const { symbol, provider } = req.query;

  const result = await analyzeStock(symbol, provider || "openrouter");

  res.status(200).json({ sentiment: result });
}
