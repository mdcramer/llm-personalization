import json
import os
from pathlib import Path

from openai import OpenAI


class OpenAIChatService:
    def __init__(self):
        self.config = self._load_config()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = self.config.get("CHAT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.prompts_dir = Path(__file__).parent / "prompts"

    def _load_config(self):
        config_path = Path(__file__).parent / "config.txt"
        config = {}

        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

        return config

    def _require_client(self):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return self.client

    def _load_prompt(self, file_name):
        prompt_path = self.prompts_dir / file_name
        return prompt_path.read_text(encoding="utf-8").strip()

    def build_embedding(self, text, model, dimensions):
        client = self._require_client()
        request = {
            "model": model,
            "input": text,
            "encoding_format": "float",
        }

        if dimensions:
            request["dimensions"] = dimensions

        response = client.embeddings.create(**request)
        return response.data[0].embedding

    def generate_cluster_labels(self, clusters):
        if not clusters:
            return {}

        client = self._require_client()
        prompt = self._load_prompt("cluster_labeling.txt")

        payload = []
        for cluster in clusters:
            payload.append(
                {
                    "cluster_id": cluster["cluster_id"],
                    "cluster_score": cluster["cluster_score"],
                    "memories": [
                        {
                            "text": memory["embedding_text"],
                            "score": memory["weight"],
                        }
                        for memory in cluster["memories"]
                    ],
                }
            )

        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps({"clusters": payload}),
                },
            ],
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        raw_labels = parsed.get("descriptions", {})
        labels = {}

        if isinstance(raw_labels, dict):
            for key, value in raw_labels.items():
                if isinstance(value, str) and value.strip():
                    labels[str(key)] = value.strip()

        return labels

    def _build_personalization_block(self, memories):
        if not memories:
            return ""

        template = self._load_prompt("personalization_injection.txt")
        lines = []

        likes = [memory["content"] for memory in memories if memory.get("memory_type") == "like"]
        dislikes = [memory["content"] for memory in memories if memory.get("memory_type") == "dislike"]

        if likes:
            lines.append("Known user likes:")
            lines.extend(f"- {item}" for item in likes)

        if dislikes:
            lines.append("Known user dislikes:")
            lines.extend(f"- {item}" for item in dislikes)

        memory_text = "\n".join(lines).strip()
        if not memory_text:
            return ""

        return template.replace("{{MEMORIES}}", memory_text)

    def get_reply(self, message, history=None, memories=None):
        history = history or []
        memories = memories or []
        client = self._require_client()
        system_prompt = self._load_prompt("chat_system.txt")
        personalization_block = self._build_personalization_block(memories)

        if personalization_block:
            system_prompt = f"{system_prompt}\n\n{personalization_block}"

        messages = [
            {
                "role": "system",
                "content": system_prompt,
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
