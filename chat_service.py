import json
import os
from pathlib import Path

from openai import OpenAI


class OpenAIChatService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.prompts_dir = Path(__file__).parent / "prompts"

    def _require_client(self):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return self.client

    def _load_prompt(self, file_name):
        prompt_path = self.prompts_dir / file_name
        return prompt_path.read_text(encoding="utf-8").strip()

    def get_reply(self, message, history=None):
        history = history or []
        client = self._require_client()

        messages = [
            {
                "role": "system",
                "content": self._load_prompt("chat_system.txt"),
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

    def extract_preferences(self, message):
        client = self._require_client()

        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": self._load_prompt("memory_extraction.txt"),
                },
                {
                    "role": "user",
                    "content": message,
                },
            ],
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        likes = [item.strip() for item in parsed.get("likes", []) if isinstance(item, str) and item.strip()]
        dislikes = [
            item.strip()
            for item in parsed.get("dislikes", [])
            if isinstance(item, str) and item.strip()
        ]

        return {"likes": likes, "dislikes": dislikes}
