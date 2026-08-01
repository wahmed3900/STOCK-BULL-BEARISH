import { togetherSentiment } from "./together_ai";
import { openrouterSentiment } from "./openrouter_ai";

export async function analyzeStock(symbol: string, provider: "openrouter" | "together") {
  const prompt = `Is ${symbol} bullish or bearish today?`;
  return provider === "together"
    ? await togetherSentiment(prompt)
    : await openrouterSentiment(prompt);
}
