from __future__ import annotations

import difflib
import re


def _tokenize(text: str) -> list[str]:
    """Split text into word-level tokens, preserving whitespace."""
    return re.findall(r"\S+|\s+", text)


def compute_diff(original: str, revised: str) -> tuple[str, str]:
    """Return Rich-markup strings for *original* and *revised* with highlights.

    Deleted words in the original are shown in red with strikethrough.
    Added words in the revised are shown in green.
    Unchanged tokens are shown as-is.
    """
    orig_tokens = _tokenize(original)
    rev_tokens = _tokenize(revised)

    matcher = difflib.SequenceMatcher(None, orig_tokens, rev_tokens, autojunk=False)

    orig_parts: list[str] = []
    rev_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        orig_chunk = "".join(orig_tokens[i1:i2])
        rev_chunk = "".join(rev_tokens[j1:j2])

        if tag == "equal":
            orig_parts.append(_escape(orig_chunk))
            rev_parts.append(_escape(rev_chunk))
        elif tag == "delete":
            orig_parts.append(f"[bold red strike]{_escape(orig_chunk)}[/]")
        elif tag == "insert":
            rev_parts.append(f"[bold green]{_escape(rev_chunk)}[/]")
        elif tag == "replace":
            orig_parts.append(f"[bold red strike]{_escape(orig_chunk)}[/]")
            rev_parts.append(f"[bold green]{_escape(rev_chunk)}[/]")

    return "".join(orig_parts), "".join(rev_parts)


def _escape(text: str) -> str:
    """Escape Rich markup special characters."""
    return text.replace("[", "\\[").replace("]", "\\]")
