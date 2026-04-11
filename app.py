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

    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=True, host="127.0.0.1", port=port)
