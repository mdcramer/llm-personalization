# Personalized Chatbot Prototype

This is a very small Flask-based chatbot prototype with:

- a single HTML/JavaScript frontend
- a Flask backend
- an OpenAI Chat Completions passthrough
- SQLite-backed memories scoped to a browser session
- prompt templates stored as editable text files

## 1. Install Python

Use Python 3.11 or newer.

## 2. Create and activate a virtual environment

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## 3. Install dependencies

```powershell
pip install -r requirements.txt
```

## 4. Set environment variables

### Windows PowerShell

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-4o-mini"
```

## 5. Run the app

```powershell
python app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Current scope

Version 0.1 is intentionally simple:

- no authentication
- no streaming
- no persistent chat history
- no memory injection yet
- memories are per browser session, not shared across users
- memories expire and are capped to keep the demo DB from growing without bounds

The SQLite database is included now so we can add personalization later without changing the project shape too much.

## Configuration

Prototype tuning values live in `config.txt`.

Right now it includes:

- `MEMORY_TTL_DAYS`
- `MAX_MEMORIES_PER_SESSION`
- `MAX_TOTAL_MEMORIES`

Restart Flask after changing `config.txt` so the updated values are loaded.

## Prompt files

Prompt templates live in the `prompts/` folder:

- `chat_system.txt` for the main assistant behavior
- `memory_extraction.txt` for extracting likes/dislikes
- `personalization_injection.txt` as a placeholder for future prompt injection

These files are read by the backend at runtime, so you can inspect and edit them directly.
