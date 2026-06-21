"""Tests for write_cli.session — persist/restore session data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import write_cli.session as session_module
from write_cli.session import load_session, save_session


@pytest.fixture(autouse=True)
def tmp_session_path(tmp_path, monkeypatch):
    """Redirect session file to a temp directory for every test."""
    session_file = tmp_path / "session.json"
    monkeypatch.setattr(session_module, "_SESSION_PATH", session_file)
    return session_file


# ---------------------------------------------------------------------------
# load_session()
# ---------------------------------------------------------------------------


def test_load_session_returns_empty_dict_when_missing():
    assert load_session() == {}


def test_load_session_returns_saved_data(tmp_session_path):
    tmp_session_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_session_path.write_text(
        json.dumps({"input": "hello", "suggestion": "hi there"}), encoding="utf-8"
    )
    data = load_session()
    assert data["input"] == "hello"
    assert data["suggestion"] == "hi there"


def test_load_session_returns_empty_on_corrupt_file(tmp_session_path):
    tmp_session_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_session_path.write_text("not valid json{{", encoding="utf-8")
    assert load_session() == {}


def test_load_session_returns_empty_on_non_dict_json(tmp_session_path):
    tmp_session_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_session_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_session() == {}


# ---------------------------------------------------------------------------
# save_session()
# ---------------------------------------------------------------------------


def test_save_session_creates_file(tmp_session_path):
    save_session("my input", "my suggestion")
    assert tmp_session_path.exists()


def test_save_session_round_trip(tmp_session_path):
    save_session("original text", "improved text")
    data = load_session()
    assert data["input"] == "original text"
    assert data["suggestion"] == "improved text"


def test_save_session_overwrites_previous(tmp_session_path):
    save_session("first", "first suggestion")
    save_session("second", "second suggestion")
    data = load_session()
    assert data["input"] == "second"
    assert data["suggestion"] == "second suggestion"


def test_save_session_handles_unicode(tmp_session_path):
    save_session("café résumé", "café résumé improved")
    data = load_session()
    assert data["input"] == "café résumé"


def test_save_session_never_raises_on_unwritable_path(monkeypatch, tmp_path):
    """save_session must silently swallow errors."""
    unwritable = tmp_path / "no_such_dir" / "deep" / "session.json"
    monkeypatch.setattr(session_module, "_SESSION_PATH", unwritable)
    # patch mkdir to raise so the directory creation fails
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: (_ for _ in ()).throw(OSError("no perm")))
    save_session("x", "y")  # must not raise
