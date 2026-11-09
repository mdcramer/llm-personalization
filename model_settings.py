import os


def resolve_model_settings(config):
    # An explicitly blank environment setting selects the default.
    model = os.environ.get("CHAT_MODEL", config.get("CHAT_MODEL", "")).strip() or "mistral-small-latest"
    name = model.lower()
    if name.startswith(("mistral-", "ministral-", "magistral-", "codestral-", "devstral-", "pixtral-", "open-mistral-", "open-mixtral-")):
        provider = "mistral"
    elif name.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4")):
        provider = "openai"
    else:
        raise ValueError(f"Cannot determine provider for CHAT_MODEL '{model}'. Use a supported Mistral or OpenAI model name.")
    return {
        "model": model,
        "provider": provider,
        "embedding_model": "mistral-embed" if provider == "mistral" else "text-embedding-3-small",
        "embedding_dimensions": 1024 if provider == "mistral" else 256,
    }
