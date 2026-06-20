"""Persist and restore the last session (input text + suggestion)."""
from __future__ import annotations

import json
from pathlib import Path

_SESSION_PATH = Path.home() / ".config" / "rewordly" / "session.json"


def load_session() -> dict[str, str]:
    """Return saved session data, or empty dict on any error."""
    try:
        data = json.loads(_SESSION_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_session(input_text: str, suggestion: str) -> None:
    """Persist input + suggestion silently; never raises."""
    try:
        _SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_PATH.write_text(
            json.dumps({"input": input_text, "suggestion": suggestion}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
