import os

from openai import OpenAI


class OpenAIChatService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def get_reply(self, message, history=None):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")

        history = history or []
        client = OpenAI(api_key=self.api_key)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant inside a prototype personalized chatbot. "
                    "For now, behave like a clear and concise assistant."
                ),
            }
        ]

        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        return response.choices[0].message.content or ""
