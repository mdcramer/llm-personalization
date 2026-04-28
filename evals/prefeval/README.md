# PrefEval Classification Harness

Small local runner for comparing a vanilla model against preference-aware variants on
PrefEval-style multiple-choice questions.

This code does not contain an API key. It reads `OPENAI_API_KEY` from the environment
at runtime. If that variable is not set, OpenAI adapters refuse to run.

## Install

```powershell
pip install openai datasets
```

The `datasets` package downloads PrefEval into the normal Hugging Face cache, not into
this repository.

If dependencies were added or changed, run:

```powershell
pip install -r requirements.txt
```

You only need to rerun this when setting up a new environment, after pulling dependency
changes, or when an import fails because a package is missing.

Set your OpenAI key in the current Anaconda Prompt session:

```powershell
set OPENAI_API_KEY=your_key_here
```

PowerShell uses a different syntax:

```powershell
$env:OPENAI_API_KEY = "your_key_here"
```

## First Runs

Vanilla baseline:

```powershell
python evals\prefeval\run_classification.py --adapter vanilla --limit 25
```

Manual-memory upper bound:

```powershell
python evals\prefeval\run_classification.py --adapter manual-memory --limit 25
```

Prototype memory pipeline:

```powershell
python evals\prefeval\run_classification.py --adapter prototype-local --limit 25 --show-failures
```

By default, `prototype-local` runs the preference setup turn through the same
preference extractor, embedding builder, memory store, and personalized answer path
used by the app. It skips generating an assistant reply to the setup preference in
order to save tokens. To include that extra setup reply call, use:

```powershell
python evals\prefeval\run_classification.py --adapter prototype-local --limit 25 --prototype-setup-mode full-chat
```

Filter to one topic:

```powershell
python evals\prefeval\run_classification.py --adapter manual-memory --topic lifestyle_dietary --limit 25
```

Show the raw failed responses:

```powershell
python evals\prefeval\run_classification.py --adapter vanilla --limit 25 --show-failures
```

## What Is Scored

The default dataset is `siyanzhao/prefeval_implicit_choice`, because it includes:

- `preference`
- `question`
- `options`
- `aligned_op`, the preference-compatible option
- `topic`

For each row, the runner shuffles the options deterministically, asks the model to
return exactly one letter, and scores whether the chosen option equals `aligned_op`.

## Interpreting Results

The first useful comparison is:

```text
vanilla accuracy vs manual-memory accuracy
```

`vanilla` sees only the question and choices. It does not receive the preference, so a
low score is expected. `manual-memory` receives the preference directly in the prompt,
so it is an upper-bound check: if this score is high, the dataset labels, prompting,
and scoring code are probably working.

On a small 25-example sample, it is not surprising to see results like:

```text
vanilla:       7/25  = 0.280
manual-memory: 25/25 = 1.000
```

That does not prove the full memory system works yet. It says the task has a strong
preference signal, and the model can use that signal when it is handed the preference.
The next comparison is `prototype-http`, which tests whether the prototype can extract
the preference in one chat and use it in a later chat.

## Hugging Face Warnings

You may see:

```text
Warning: You are sending unauthenticated requests to the HF Hub.
```

This is fine for small local runs. It means the dataset was downloaded without a
Hugging Face token, so Hugging Face may apply lower rate limits.

On Windows, you may also see a symlink cache warning. That is also fine. Hugging Face
can still cache the dataset, but it may use a little more disk space unless Windows
Developer Mode or administrator symlink support is enabled.

## Adapters

- `vanilla`: sends only the question and options.
- `manual-memory`: sends the preference in the prompt, then the question and options.
- `prototype-local`: imports the local app code and uses a temporary eval memory
  database. It sends the preference through extraction/storage, then asks the question
  in a new chat with the stored memories.
- `prototype-http`: sends the preference to a local prototype endpoint, then asks the
  question in a new chat. This is a thin placeholder adapter meant to be adjusted to
  your actual local API.

Required environment for `prototype-http`:

```powershell
$env:PREFEVAL_PROTOTYPE_BASE_URL = "http://localhost:3000"
```

Optional:

```powershell
$env:PREFEVAL_PROTOTYPE_API_KEY = "local-dev-token"
```

Expected prototype endpoints:

- `POST /eval/users` with `{ "user_id": "..." }`
- `POST /eval/users/{user_id}/chats` with `{}` returning `{ "chat_id": "..." }`
- `POST /eval/chats/{chat_id}/messages` with `{ "message": "..." }` returning `{ "content": "..." }`

If your prototype uses different endpoints, edit `PrototypeHttpAdapter` in
`run_classification.py`.

