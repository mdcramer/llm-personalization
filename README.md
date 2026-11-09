# Personalized Chatbot Prototype

This is a very small Flask-based chatbot prototype with:

- a single HTML/JavaScript frontend
- a Flask backend
- configurable Mistral or OpenAI chat
- SQLite-backed memories scoped to a browser session
- provider-matched embeddings for stored memories
- DBSCAN clustering for semantically similar memories
- LLM-generated cluster descriptions plus per-memory alignment markers
- prompt-based personalization injection during chat
- prompt templates stored as editable text files

## Run locally with Anaconda Prompt

If PowerShell is giving you trouble, use **Anaconda Prompt** instead.

## 1. Open Anaconda Prompt

Open the Anaconda Prompt from the Start menu.

## 2. Go to the project folder

```bat
cd C:\Users\markd\Documents\GitHub\llm-personalization
```

## 3. Create a Conda environment

Use Python 3.11 or newer.

```bat
conda create -n llm-personalization python=3.11 -y
```

## 4. Activate the environment

```bat
conda activate llm-personalization
```

## 5. Install dependencies

```bat
pip install -r requirements.txt
```

## 6. Set environment variables

```bat
set OPENAI_API_KEY=your_api_key_here
set MISTRAL_API_KEY=your_mistral_key_here
```

The default model is `mistral-small-latest`; only `MISTRAL_API_KEY` is needed.
For OpenAI instead, set `CHAT_MODEL=gpt-4o-mini` and `OPENAI_API_KEY`.

## 7. Run the app

```bat
python app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Optional: PowerShell workflow

If you want to use PowerShell later, this repo also works with a regular virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY="your_api_key_here"
$env:MISTRAL_API_KEY="your_mistral_key_here"
python app.py
```

## Current scope

Version 0.1 is intentionally simple:

- no authentication
- no streaming
- no persistent chat history
- memories are injected into the chat prompt for personalization
- memories are per browser session, not shared across users
- memories expire and are capped to keep the demo DB from growing without bounds
- memory clusters are generated from embeddings and labeled by an LLM

The SQLite database is included now so we can add personalization later without changing the project shape too much.

## Configuration

Prototype tuning values live in `config.txt`.

Right now it includes:

- `MEMORY_TTL_DAYS`
- `MAX_MEMORIES_PER_SESSION`
- `MAX_TOTAL_MEMORIES`
- `WEIGHT_HALF_LIFE_MINUTES`
- `CLUSTER_EPSILON`
- `CLUSTER_MIN_SAMPLES`
- `CHAT_MODEL`
- Embedding model and dimensions are selected automatically from `CHAT_MODEL`.

Restart Flask after changing `config.txt` so the updated values are loaded.

## Railway deployment notes

For Railway deployment:

- the app can be started with the included `Procfile`
- set `OPENAI_API_KEY` only if selecting an OpenAI model
- set `MISTRAL_API_KEY` for Mistral chat
- optionally set `CHAT_MODEL`; blank defaults to `mistral-small-latest`
- set `MEMORY_DB_PATH=/data/memory.db` if you attach a Railway volume mounted at `/data`

Using a persistent volume is recommended if you want SQLite memories to survive redeploys and restarts.

## Prompt files

Prompt templates live in the `prompts/` folder:

- `chat_system.txt` for the main assistant behavior
- `memory_extraction.txt` for extracting likes/dislikes
- `personalization_injection.txt` for injecting memories into chat prompts
- `cluster_labeling.txt` for generating short labels for memory clusters

These files are read by the backend at runtime, so you can inspect and edit them directly.

## Selecting a model

`CHAT_MODEL` is the only model setting. Its environment variable overrides
`config.txt`; a blank value defaults to `mistral-small-latest`.
Mistral model names select the Mistral API and `MISTRAL_API_KEY`, with
`mistral-embed` embeddings (1024 dimensions). OpenAI model names such as
`gpt-4o-mini` select the OpenAI API and `OPENAI_API_KEY`, with
`text-embedding-3-small` embeddings (256 dimensions).

Replies, preference extraction, cluster annotations, and embeddings all use the
selected provider. Unsupported model name families fail with a configuration error.
`CHAT_PROVIDER`, `OPENAI_MODEL`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS`
are no longer used; remove old variables to avoid confusion. Keys belong only in
environment variables. There is no automatic provider fallback.

Deploy these code changes once. Later model changes in Railway variables require
applying a service redeploy/restart, with no source changes. Changes to `config.txt`
require deploying the changed file. Only the selected provider's key is required.

When switching providers, reset old memories using the app's reset control for
a fresh start. Existing vectors from a different embedding model are excluded
from clustering so incompatible vector spaces are never compared. Existing memory
text is retained until reset or expiry. Clustering thresholds may need tuning
when changing embedding models.
