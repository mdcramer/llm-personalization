# Personalized Chatbot Prototype

This is a very small Flask-based chatbot prototype with:

- a single HTML/JavaScript frontend
- a Flask backend
- an OpenAI Chat Completions passthrough
- SQLite-backed memories scoped to a browser session
- OpenAI embeddings for stored memories
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
set OPENAI_MODEL=gpt-4o-mini
```

If you want to keep using the repo's default chat model, you can skip `OPENAI_MODEL`.

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
$env:OPENAI_MODEL="gpt-4o-mini"
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
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`

Restart Flask after changing `config.txt` so the updated values are loaded.

## Railway deployment notes

For Railway deployment:

- the app can be started with the included `Procfile`
- set `OPENAI_API_KEY` in Railway variables
- optionally set `OPENAI_MODEL`
- set `MEMORY_DB_PATH=/data/memory.db` if you attach a Railway volume mounted at `/data`

Using a persistent volume is recommended if you want SQLite memories to survive redeploys and restarts.

## Prompt files

Prompt templates live in the `prompts/` folder:

- `chat_system.txt` for the main assistant behavior
- `memory_extraction.txt` for extracting likes/dislikes
- `personalization_injection.txt` for injecting memories into chat prompts
- `cluster_labeling.txt` for generating short labels for memory clusters

These files are read by the backend at runtime, so you can inspect and edit them directly.
