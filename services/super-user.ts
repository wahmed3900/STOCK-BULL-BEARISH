export async function analyzePremium(symbol: string) {
  return await togetherSentiment(
    `Give a deep analysis of ${symbol}. Include risks, trends, and reasoning.`
  );
}
