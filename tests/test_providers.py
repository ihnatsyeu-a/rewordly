"""Tests for AI providers."""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from write_cli.providers._openai_compat import (
    OpenAICompatibleProvider,
    _build_prompt,
    _MODE_INSTRUCTIONS,
)
from write_cli.providers.github import GitHubModelsProvider, _GITHUB_BASE_URL
from write_cli.providers.openai_provider import OpenAIProvider
from write_cli.providers.gemini import GeminiProvider, _GEMINI_BASE_URL
from write_cli.providers.ollama import OllamaProvider, _OLLAMA_BASE_URL, _OLLAMA_GENERATE_URL


# ---------------------------------------------------------------------------
# _build_prompt()
# ---------------------------------------------------------------------------


def test_build_prompt_rephrase_contains_text():
    prompt = _build_prompt("Hello world", "rephrase", "formal", "English")
    assert "Hello world" in prompt
    assert "English" in prompt
    assert "formal" in prompt


def test_build_prompt_grammar_does_not_mention_tone():
    prompt = _build_prompt("test text", "grammar", "casual", "French")
    assert "test text" in prompt
    assert "French" in prompt
    # grammar mode preserves author voice — tone instruction should not appear
    assert "casual" not in prompt


def test_build_prompt_alternative_contains_text():
    prompt = _build_prompt("sample", "alternative", "friendly", "Spanish")
    assert "sample" in prompt
    assert "friendly" in prompt
    assert "Spanish" in prompt


def test_build_prompt_unknown_mode_falls_back_to_rephrase():
    prompt = _build_prompt("text", "nonexistent_mode", "formal", "English")
    rephrase_prompt = _build_prompt("text", "rephrase", "formal", "English")
    assert prompt == rephrase_prompt


def test_build_prompt_structure():
    prompt = _build_prompt("My text.", "rephrase", "formal", "English")
    assert "Text:" in prompt
    assert "My text." in prompt


# ---------------------------------------------------------------------------
# Provider base URL / api_key wiring
# ---------------------------------------------------------------------------


def test_github_provider_uses_correct_base_url():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI") as mock_openai:
        GitHubModelsProvider("ghp_test")
        mock_openai.assert_called_once_with(api_key="ghp_test", base_url=_GITHUB_BASE_URL)


def test_openai_provider_uses_no_base_url():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI") as mock_openai:
        OpenAIProvider("sk-test")
        mock_openai.assert_called_once_with(api_key="sk-test", base_url=None)


def test_gemini_provider_uses_correct_base_url():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI") as mock_openai:
        GeminiProvider("AIza-test")
        mock_openai.assert_called_once_with(api_key="AIza-test", base_url=_GEMINI_BASE_URL)


def test_ollama_provider_uses_correct_base_url():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI") as mock_openai:
        OllamaProvider()
        mock_openai.assert_called_once_with(api_key="ollama", base_url=_OLLAMA_BASE_URL)


# ---------------------------------------------------------------------------
# stream_suggestion() — mocked urllib
# ---------------------------------------------------------------------------

import io


def _make_urllib_response(content: str):
    import json as _json
    body = _json.dumps({"response": content, "done": True}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=body)
    return mock_resp


async def _async_iter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_stream_suggestion_yields_tokens():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI"):
        provider = OllamaProvider()

    with patch("write_cli.providers.ollama.urllib.request.urlopen",
               return_value=_make_urllib_response("Hello world")):
        tokens = []
        async for token in provider.stream_suggestion(
            text="Fix this.", mode="grammar", tone="formal", language="English", model="gemma3:1b"
        ):
            tokens.append(token)

    assert tokens == ["Hello world"]


@pytest.mark.asyncio
async def test_stream_suggestion_skips_empty_chunks():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI"):
        provider = OllamaProvider()

    with patch("write_cli.providers.ollama.urllib.request.urlopen",
               return_value=_make_urllib_response("ok")):
        tokens = []
        async for token in provider.stream_suggestion(
            text="Hello", mode="rephrase", tone="casual", language="English", model="gemma3:1b"
        ):
            tokens.append(token)

    assert tokens == ["ok"]


@pytest.mark.asyncio
async def test_stream_suggestion_skips_no_choices():
    with patch("write_cli.providers._openai_compat.AsyncOpenAI"):
        provider = OllamaProvider()

    with patch("write_cli.providers.ollama.urllib.request.urlopen",
               return_value=_make_urllib_response("result")):
        tokens = []
        async for token in provider.stream_suggestion(
            text="Hello", mode="rephrase", tone="formal", language="English", model="gemma3:1b"
        ):
            tokens.append(token)

    assert tokens == ["result"]


@pytest.mark.asyncio
async def test_stream_suggestion_passes_correct_model():
    mock_urlopen = MagicMock(return_value=_make_urllib_response("done"))

    with patch("write_cli.providers._openai_compat.AsyncOpenAI"):
        provider = OllamaProvider()

    with patch("write_cli.providers.ollama.urllib.request.urlopen", mock_urlopen):
        async for _ in provider.stream_suggestion(
            text="test", mode="rephrase", tone="formal", language="English", model="gemma3:4b"
        ):
            pass

    req = mock_urlopen.call_args.args[0]
    body = json.loads(req.data.decode())
    assert body["model"] == "gemma3:4b"
    assert body["stream"] is False
    assert req.full_url == _OLLAMA_GENERATE_URL
