from openai import OpenAI


class OpenAISummarizer:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required to summarize articles.")

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def summarize(self, text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Summarize news articles clearly and concisely.",
                },
                {
                    "role": "user",
                    "content": f"Summarize this article in 3 bullet points:\n\n{text}",
                },
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
