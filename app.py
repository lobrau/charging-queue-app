import os
import threading
import time
import uuid
from dataclasses import dataclass, asdict

from flask import Flask, jsonify, render_template, request, session

EXPIRY_SECONDS = 10 * 60 * 60

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me-in-prod")

_lock = threading.Lock()
_queue: list[dict] = []


@dataclass
class Entry:
    id: str
    name: str
    owner: str
    added_at: float
    charging: bool = False


def _prune(now: float) -> None:
    global _queue
    _queue = [e for e in _queue if now - e["added_at"] < EXPIRY_SECONDS]


def _get_owner() -> str:
    if "owner" not in session:
        session["owner"] = uuid.uuid4().hex
        session.permanent = True
    return session["owner"]


@app.route("/")
def index():
    _get_owner()
    return render_template("index.html")


@app.route("/api/queue")
def list_queue():
    owner = _get_owner()
    now = time.time()
    with _lock:
        _prune(now)
        result = [
            {
                "id": e["id"],
                "name": e["name"],
                "mine": e["owner"] == owner,
                "charging": e["charging"],
                "seconds_remaining": int(EXPIRY_SECONDS - (now - e["added_at"])),
            }
            for e in _queue
        ]
    return jsonify(result)


@app.route("/api/queue/join", methods=["POST"])
def join():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if len(name) > 60:
        return jsonify({"error": "name too long"}), 400

    owner = _get_owner()
    entry = Entry(
        id=uuid.uuid4().hex,
        name=name,
        owner=owner,
        added_at=time.time(),
    )
    with _lock:
        _prune(entry.added_at)
        _queue.append(asdict(entry))
    return jsonify({"id": entry.id}), 201


@app.route("/api/queue/leave/<entry_id>", methods=["POST"])
def leave(entry_id: str):
    owner = _get_owner()
    with _lock:
        for i, e in enumerate(_queue):
            if e["id"] == entry_id:
                if e["owner"] != owner:
                    return jsonify({"error": "not your entry"}), 403
                _queue.pop(i)
                return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


@app.route("/api/queue/charging/<entry_id>", methods=["POST"])
def set_charging(entry_id: str):
    data = request.get_json(silent=True) or {}
    charging = bool(data.get("charging"))
    owner = _get_owner()
    with _lock:
        for e in _queue:
            if e["id"] == entry_id:
                if e["owner"] != owner:
                    return jsonify({"error": "not your entry"}), 403
                e["charging"] = charging
                return jsonify({"ok": True, "charging": charging})
    return jsonify({"error": "not found"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
