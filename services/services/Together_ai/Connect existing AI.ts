export async function runModel(model: string, prompt: string) {
  const modelMap = {
    "openrouter/free": "openai/gpt-3.5-turbo",
    "together/llama70b": "meta-llama/Meta-Llama-3.1-70B-Instruct",
    "together/llama405b": "meta-llama/Meta-Llama-3.1-405B-Instruct",
    "together/deepseek": "deepseek-ai/DeepSeek-R1",
    "together/qwen110b": "Qwen/Qwen2.5-110B-Instruct"
  };

  const completion = await together.chat.completions.create({
    model: modelMap[model],
    messages: [{ role: "user", content: prompt }],
  });

  return completion.choices[0].message.content;
}
