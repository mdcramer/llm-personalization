import argparse
import json
import os
import random
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class Example:
    idx: int
    preference: str
    question: str
    options: List[str]
    aligned_option: str
    topic: str
    explanation: str = ""


@dataclass
class Result:
    idx: int
    topic: str
    correct_letter: str
    predicted_letter: Optional[str]
    correct: bool
    raw_response: str


class Adapter:
    name = "adapter"

    def answer(self, example: Example, options: Sequence[Tuple[str, str]]) -> str:
        raise NotImplementedError


class OpenAIAdapter(Adapter):
    def __init__(self, model: str, mode: str):
        self.model = model
        self.mode = mode
        self.name = mode
        self._client = None

    @property
    def client(self):
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def answer(self, example: Example, options: Sequence[Tuple[str, str]]) -> str:
        messages = build_openai_messages(example, options, include_preference=self.mode == "manual-memory")
        return call_openai(self.client, self.model, messages)


class PrototypeHttpAdapter(Adapter):
    name = "prototype-http"

    def __init__(self):
        base_url = os.environ.get("PREFEVAL_PROTOTYPE_BASE_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError("PREFEVAL_PROTOTYPE_BASE_URL is not set.")
        self.base_url = base_url
        self.api_key = os.environ.get("PREFEVAL_PROTOTYPE_API_KEY")

    def answer(self, example: Example, options: Sequence[Tuple[str, str]]) -> str:
        user_id = f"prefeval-mode1-{example.idx}"
        self._post("/eval/users", {"user_id": user_id})

        setup_chat = self._post(f"/eval/users/{user_id}/chats", {})
        setup_chat_id = setup_chat.get("chat_id")
        if not setup_chat_id:
            raise RuntimeError("Prototype did not return chat_id for setup chat.")
        self._post(f"/eval/chats/{setup_chat_id}/messages", {"message": example.preference})

        question_chat = self._post(f"/eval/users/{user_id}/chats", {})
        question_chat_id = question_chat.get("chat_id")
        if not question_chat_id:
            raise RuntimeError("Prototype did not return chat_id for question chat.")

        prompt = build_mcq_prompt(example.question, options)
        response = self._post(f"/eval/chats/{question_chat_id}/messages", {"message": prompt})
        return str(response.get("content", ""))

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Prototype HTTP {exc.code} for {path}: {detail}") from exc
        return json.loads(data) if data else {}


class PrototypeLocalAdapter(Adapter):
    name = "prototype-local"

    def __init__(self, setup_mode: str):
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from chat_service import OpenAIChatService
        from memory import MemoryStore

        self.chat_service = OpenAIChatService()
        db_path = Path(tempfile.gettempdir()) / f"prefeval-memory-{os.getpid()}.db"
        self.memory_store = MemoryStore(db_path)
        self.setup_mode = setup_mode

    def answer(self, example: Example, options: Sequence[Tuple[str, str]]) -> str:
        session_id = f"prefeval-mode1-{example.idx}"
        self.memory_store.clear_memories(session_id)
        self._store_preferences(session_id, example.preference)

        memories = self.memory_store.list_memories(session_id)
        prompt = build_mcq_prompt(example.question, options)
        return self.chat_service.get_reply(message=prompt, history=[], memories=memories)

    def _store_preferences(self, session_id: str, preference: str) -> None:
        if self.setup_mode == "full-chat":
            self.chat_service.get_reply(message=preference, history=[], memories=[])

        extraction_result = self.chat_service.extract_preferences(preference)
        embedding_settings = self.memory_store.get_embedding_settings()
        for item in extraction_result["likes"]:
            self._add_memory(session_id, "like", item, 1.0, embedding_settings)
        for item in extraction_result["dislikes"]:
            self._add_memory(session_id, "dislike", item, -1.0, embedding_settings)

        self.memory_store.enforce_limits(session_id)
        self.memory_store.recluster_memories(session_id)

    def _add_memory(
        self,
        session_id: str,
        memory_type: str,
        content: str,
        weight: float,
        embedding_settings: Dict[str, Any],
    ) -> None:
        embedding_text = normalize_embedding_text(content)
        embedding_vector = self.chat_service.build_embedding(
            embedding_text,
            embedding_settings["embedding_model"],
            embedding_settings["embedding_dimensions"],
        )
        self.memory_store.add_memory(
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            weight=weight,
            embedding_text=embedding_text,
            embedding_model=embedding_settings["embedding_model"],
            embedding_dimensions=embedding_settings["embedding_dimensions"],
            embedding=json.dumps(embedding_vector),
        )


def load_examples(dataset_name: str, split: str, topic: Optional[str], limit: Optional[int], seed: int) -> List[Example]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install the datasets package first: pip install datasets") from exc

    dataset = load_dataset(dataset_name, split=split)
    examples: List[Example] = []
    for idx, row in enumerate(dataset):
        row_topic = str(row.get("topic", ""))
        if topic and row_topic != topic:
            continue
        options = list(row.get("options") or [])
        aligned = str(row.get("aligned_op", ""))
        if not options or not aligned:
            continue
        examples.append(
            Example(
                idx=idx,
                preference=str(row.get("preference", "")),
                question=str(row.get("question", "")),
                options=[str(option) for option in options],
                aligned_option=aligned,
                topic=row_topic,
                explanation=str(row.get("explanation", "")),
            )
        )

    rng = random.Random(seed)
    rng.shuffle(examples)
    return examples[:limit] if limit else examples


def shuffled_options(example: Example, seed: int) -> Tuple[List[Tuple[str, str]], str]:
    options = list(example.options)
    rng = random.Random(seed + example.idx)
    rng.shuffle(options)
    correct_index = options.index(example.aligned_option)
    labeled = [(LETTERS[i], option) for i, option in enumerate(options)]
    return labeled, LETTERS[correct_index]


def build_mcq_prompt(question: str, options: Sequence[Tuple[str, str]]) -> str:
    option_text = "\n".join(f"{letter}. {text}" for letter, text in options)
    return (
        "Choose the single best answer for the user.\n\n"
        f"Question: {question}\n\n"
        f"Options:\n{option_text}\n\n"
        "Reply with only the letter of the best option."
    )


def build_openai_messages(
    example: Example,
    options: Sequence[Tuple[str, str]],
    include_preference: bool,
) -> List[Dict[str, str]]:
    system = (
        "You answer multiple-choice preference-following questions. "
        "Return only one capital letter, with no explanation."
    )
    user_parts = []
    if include_preference:
        user_parts.append(f"Known user preference: {example.preference}")
    user_parts.append(build_mcq_prompt(example.question, options))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def normalize_embedding_text(content: str) -> str:
    return content.strip().lower().rstrip(".!?")


def call_openai(client: Any, model: str, messages: List[Dict[str, str]]) -> str:
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            temperature=0,
            max_output_tokens=16,
        )
        text = getattr(response, "output_text", None)
        if text is not None:
            return text
    except AttributeError:
        pass

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=8,
    )
    return response.choices[0].message.content or ""


def extract_letter(text: str, valid_letters: Iterable[str]) -> Optional[str]:
    valid = set(valid_letters)
    stripped = text.strip().upper()
    if stripped in valid:
        return stripped
    match = re.search(r"\b([A-Z])\b", stripped)
    if match and match.group(1) in valid:
        return match.group(1)
    return None


def make_adapter(name: str, model: str, prototype_setup_mode: str) -> Adapter:
    if name == "vanilla":
        return OpenAIAdapter(model=model, mode="vanilla")
    if name == "manual-memory":
        return OpenAIAdapter(model=model, mode="manual-memory")
    if name == "prototype-local":
        return PrototypeLocalAdapter(setup_mode=prototype_setup_mode)
    if name == "prototype-http":
        return PrototypeHttpAdapter()
    raise ValueError(f"Unknown adapter: {name}")


def run(args: argparse.Namespace) -> int:
    adapter = make_adapter(args.adapter, args.model, args.prototype_setup_mode)
    examples = load_examples(args.dataset, args.split, args.topic, args.limit, args.seed)
    if not examples:
        print("No examples matched the requested filters.")
        return 1

    print(f"Adapter: {adapter.name}")
    print(f"Dataset: {args.dataset} [{args.split}]")
    print(f"Topic: {args.topic or 'all'}")
    print(f"Examples: {len(examples)}")
    print("")

    results: List[Result] = []
    started = time.time()
    for count, example in enumerate(examples, start=1):
        options, correct_letter = shuffled_options(example, args.seed)
        raw = adapter.answer(example, options)
        prediction = extract_letter(raw, [letter for letter, _ in options])
        correct = prediction == correct_letter
        results.append(
            Result(
                idx=example.idx,
                topic=example.topic,
                correct_letter=correct_letter,
                predicted_letter=prediction,
                correct=correct,
                raw_response=raw,
            )
        )
        status = "ok" if correct else "wrong"
        shown_prediction = prediction or "invalid"
        print(
            f"{count:>4}/{len(examples)} {status:<7} "
            f"topic={example.topic} expected={correct_letter} got={shown_prediction}"
        )

    correct_count = sum(1 for result in results if result.correct)
    invalid_count = sum(1 for result in results if result.predicted_letter is None)
    elapsed = time.time() - started
    accuracy = correct_count / len(results)
    invalid_rate = invalid_count / len(results)

    print("")
    print("Summary")
    print(f"  correct:      {correct_count}/{len(results)}")
    print(f"  accuracy:     {accuracy:.3f}")
    print(f"  invalid_rate: {invalid_rate:.3f}")
    print(f"  elapsed_sec:  {elapsed:.1f}")

    if args.show_failures:
        print("")
        print("Failures")
        for result in results:
            if result.correct:
                continue
            raw = result.raw_response.replace("\n", " ").strip()
            print(
                f"  idx={result.idx} topic={result.topic} "
                f"expected={result.correct_letter} got={result.predicted_letter or 'invalid'} raw={raw!r}"
            )

    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PrefEval classification mode 1.")
    parser.add_argument(
        "--adapter",
        choices=["vanilla", "manual-memory", "prototype-local", "prototype-http"],
        required=True,
        help="Which backend to evaluate.",
    )
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for OpenAI adapters.")
    parser.add_argument("--dataset", default="siyanzhao/prefeval_implicit_choice")
    parser.add_argument("--split", default="train")
    parser.add_argument("--topic", help="Optional exact topic filter, e.g. lifestyle_dietary.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum examples to run.")
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed for examples and options.")
    parser.add_argument("--show-failures", action="store_true")
    parser.add_argument(
        "--prototype-setup-mode",
        choices=["extract-only", "full-chat"],
        default="extract-only",
        help="How prototype-local should process the preference setup turn.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))

