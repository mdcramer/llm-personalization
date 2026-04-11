import os
import secrets

from flask import Flask, jsonify, make_response, render_template, request

from chat_service import OpenAIChatService
from memory import MemoryStore


app = Flask(__name__)

chat_service = OpenAIChatService()
memory_store = MemoryStore(os.getenv("MEMORY_DB_PATH", "memory.db"))
SESSION_COOKIE_NAME = "chatbot_session_id"


def get_or_create_session_id():
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        return session_id, False
    return secrets.token_urlsafe(16), True


def attach_session_cookie(response, session_id, is_new_session):
    if is_new_session:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite="Lax",
        )
    return response


@app.get("/")
def index():
    session_id, is_new_session = get_or_create_session_id()
    response = make_response(render_template("index.html"))
    return attach_session_cookie(response, session_id, is_new_session)


@app.get("/memories")
def memories():
    session_id, is_new_session = get_or_create_session_id()
    memory_store.enforce_limits(session_id)
    response = jsonify(
        {
            "memories": memory_store.list_memories(session_id),
            "limits": memory_store.get_limits(),
        }
    )
    return attach_session_cookie(response, session_id, is_new_session)


@app.post("/memories/clear")
def clear_memories():
    session_id, is_new_session = get_or_create_session_id()
    memory_store.clear_memories(session_id)
    print(f"[memory] cleared memories for session {session_id[:8]}")
    response = jsonify(
        {
            "ok": True,
            "memories": [],
            "limits": memory_store.get_limits(),
        }
    )
    return attach_session_cookie(response, session_id, is_new_session)


@app.post("/chat")
def chat():
    session_id, is_new_session = get_or_create_session_id()
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []

    if not message:
        response = jsonify({"error": "Message is required."})
        response.status_code = 400
        return attach_session_cookie(response, session_id, is_new_session)

    try:
        reply = chat_service.get_reply(message=message, history=history)
    except RuntimeError as exc:
        response = jsonify({"error": str(exc)})
        response.status_code = 500
        return attach_session_cookie(response, session_id, is_new_session)
    except Exception as exc:
        response = jsonify({"error": f"Unexpected server error: {exc}"})
        response.status_code = 500
        return attach_session_cookie(response, session_id, is_new_session)

    extraction_result = {"likes": [], "dislikes": []}

    try:
        extraction_result = chat_service.extract_preferences(message)
        for item in extraction_result["likes"]:
            if memory_store.add_memory(session_id, "like", item):
                print(f"[memory] stored like for {session_id[:8]}: {item}")
        for item in extraction_result["dislikes"]:
            if memory_store.add_memory(session_id, "dislike", item):
                print(f"[memory] stored dislike for {session_id[:8]}: {item}")
    except Exception as exc:
        print(f"[memory] extraction skipped for {session_id[:8]} due to error: {exc}")

    memory_store.enforce_limits(session_id)
    response = jsonify(
        {
            "reply": reply,
            "extracted": extraction_result,
            "memories": memory_store.list_memories(session_id),
            "limits": memory_store.get_limits(),
        }
    )
    return attach_session_cookie(response, session_id, is_new_session)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=True, host="127.0.0.1", port=port)
