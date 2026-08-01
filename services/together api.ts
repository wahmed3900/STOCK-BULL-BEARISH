import Together from "together-ai";

const together = new Together({
  apiKey: process.env.TOGETHER_API_KEY
});

async function main() {
  const response = await together.chat.completions.create({
    model: "openai/gpt-oss-20b",
    messages: [
      {
        role: "user",
        content: "What are some fun things to do in New York?"
      }
    ]
  });

  console.log(response.choices[0].message.content);
}

main();
