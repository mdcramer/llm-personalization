import os

from flask import Flask, jsonify, render_template, request

from chat_service import OpenAIChatService
from memory import MemoryStore


app = Flask(__name__)

chat_service = OpenAIChatService()
memory_store = MemoryStore()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/memories")
def memories():
    return jsonify({"memories": memory_store.list_memories()})


@app.post("/memories/clear")
def clear_memories():
    memory_store.clear_memories()
    print("[memory] cleared all memories")
    return jsonify({"ok": True, "memories": []})


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []

    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        reply = chat_service.get_reply(message=message, history=history)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Unexpected server error: {exc}"}), 500

    extraction_result = {"likes": [], "dislikes": []}

    try:
        extraction_result = chat_service.extract_preferences(message)
        for item in extraction_result["likes"]:
            if memory_store.add_memory("like", item):
                print(f"[memory] stored like: {item}")
        for item in extraction_result["dislikes"]:
            if memory_store.add_memory("dislike", item):
                print(f"[memory] stored dislike: {item}")
    except Exception as exc:
        print(f"[memory] extraction skipped due to error: {exc}")

    return jsonify(
        {
            "reply": reply,
            "extracted": extraction_result,
            "memories": memory_store.list_memories(),
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=True, host="127.0.0.1", port=port)
