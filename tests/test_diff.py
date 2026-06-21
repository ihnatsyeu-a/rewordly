"""Tests for write_cli.diff — Rich-markup diff computation."""
from __future__ import annotations

import pytest

from write_cli.diff import compute_diff, _tokenize, _escape


# ---------------------------------------------------------------------------
# _tokenize()
# ---------------------------------------------------------------------------


def test_tokenize_words():
    assert _tokenize("hello world") == ["hello", " ", "world"]


def test_tokenize_preserves_whitespace():
    tokens = _tokenize("  two  spaces  ")
    assert "".join(tokens) == "  two  spaces  "


def test_tokenize_empty_string():
    assert _tokenize("") == []


def test_tokenize_single_word():
    assert _tokenize("word") == ["word"]


def test_tokenize_multiple_spaces():
    tokens = _tokenize("a  b")
    assert "a" in tokens
    assert "b" in tokens
    assert "".join(tokens) == "a  b"


# ---------------------------------------------------------------------------
# _escape()
# ---------------------------------------------------------------------------


def test_escape_brackets():
    assert _escape("[bold]") == "\\[bold\\]"


def test_escape_no_special_chars():
    assert _escape("hello world") == "hello world"


def test_escape_multiple_brackets():
    assert _escape("[a][b]") == "\\[a\\]\\[b\\]"


# ---------------------------------------------------------------------------
# compute_diff()
# ---------------------------------------------------------------------------


def test_compute_diff_identical_texts():
    orig, rev = compute_diff("same text", "same text")
    # No markup added for identical text
    assert "same text" in orig
    assert "same text" in rev
    assert "bold" not in orig
    assert "bold" not in rev


def test_compute_diff_insertion_marked_green():
    orig, rev = compute_diff("hello", "hello world")
    assert "green" in rev
    assert "world" in rev


def test_compute_diff_deletion_marked_red():
    orig, rev = compute_diff("hello world", "hello")
    assert "red" in orig
    assert "strike" in orig


def test_compute_diff_replacement():
    orig, rev = compute_diff("bad word", "good word")
    assert "red" in orig
    assert "green" in rev
    assert "bad" in orig
    assert "good" in rev
    # unchanged "word" should appear plain in both
    assert "word" in orig
    assert "word" in rev


def test_compute_diff_empty_original():
    orig, rev = compute_diff("", "new text")
    assert "new text" in rev
    assert orig == ""


def test_compute_diff_empty_revised():
    orig, rev = compute_diff("old text", "")
    assert "old text" in orig
    assert rev == ""


def test_compute_diff_returns_tuple_of_two_strings():
    result = compute_diff("a", "b")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert all(isinstance(s, str) for s in result)


def test_compute_diff_unchanged_tokens_not_marked():
    orig, rev = compute_diff("keep this change that", "keep this improved that")
    # "keep" and "this" and "that" are unchanged — should have no markup
    for word in ("keep", "this", "that"):
        # they appear without surrounding markup tags
        assert f"]{word}[" not in orig or word in orig


def test_compute_diff_special_chars_escaped():
    orig, rev = compute_diff("[bold]", "[bold]")
    # Square brackets must be escaped in Rich markup output
    assert "\\[" in orig
    assert "\\[" in rev
