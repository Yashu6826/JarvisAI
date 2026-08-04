"""Small persistent todo store for the local NEXA assistant."""

from __future__ import annotations

import json
import hashlib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from Backend.GoogleOAuth import current_session_id


ROOT = Path(__file__).resolve().parent
TODO_FILE = ROOT / "Data" / "Todos.json"
SESSION_DATA_DIR = ROOT / "Data" / "Sessions"
_lock = threading.Lock()


def _todo_path() -> Path:
    session_id = current_session_id()
    if not session_id:
        return TODO_FILE
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return SESSION_DATA_DIR / session_key / "Todos.json"


def _read() -> list[dict]:
    path = _todo_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write(items: list[dict]) -> None:
    path = _todo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def list_todos(include_completed: bool = False) -> list[dict]:
    with _lock:
        items = _read()
    return items if include_completed else [item for item in items if not item.get("completed")]


def add_todo(task: str, due: str = "") -> dict:
    item = {
        "id": uuid.uuid4().hex[:8],
        "task": " ".join(task.split()),
        "due": " ".join(due.split()),
        "completed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        items = _read()
        items.insert(0, item)
        _write(items)
    return item


def _find(items: list[dict], query: str) -> dict | None:
    query = query.strip().lower()
    for item in items:
        if item.get("id") == query:
            return item
    for item in items:
        if query and query in str(item.get("task", "")).lower():
            return item
    return None


def complete_todo(query: str) -> dict | None:
    with _lock:
        items = _read()
        item = _find(items, query)
        if item:
            item["completed"] = True
            item["completed_at"] = datetime.now(timezone.utc).isoformat()
            _write(items)
        return item


def remove_todo(query: str) -> dict | None:
    with _lock:
        items = _read()
        item = _find(items, query)
        if not item:
            return None
        _write([candidate for candidate in items if candidate is not item])
        return item
