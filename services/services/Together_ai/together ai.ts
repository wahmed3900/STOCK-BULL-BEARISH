import OpenAI from "openai";

const together = new OpenAI({
  apiKey: process.env.TOGETHER_API_KEY,
  baseURL: "https://api.together.xyz/v1",
});

export async function togetherSentiment(prompt: string) {
  const completion = await together.chat.completions.create({
    model: "meta-llama/Meta-Llama-3.1-70B-Instruct",
    messages: [{ role: "user", content: prompt }],
  });

  return completion.choices[0].message.content;
}
