from __future__ import annotations

import asyncio
import json
import urllib.request

import httpx

from ._openai_compat import OpenAICompatibleProvider, _build_prompt

_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
_OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama provider — no API key required, uses OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        super().__init__(api_key="ollama", base_url=_OLLAMA_BASE_URL)

    async def stream_suggestion(self, text, mode, tone, language, model):
        """Call Ollama's /api/generate via a thread to avoid asyncio buffering issues."""
        prompt = _build_prompt(text, mode, tone, language)
        payload = json.dumps({
            "model": model,
            "system": "You are an expert writing assistant. When given a text, return ONLY the improved version — no explanations, no preamble, no quotation marks around the output.",
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")

        def _call() -> str:
            req = urllib.request.Request(
                _OLLAMA_GENERATE_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8")

        raw = await asyncio.get_event_loop().run_in_executor(None, _call)
        data = json.loads(raw)
        error = data.get("error")
        if error:
            raise RuntimeError(f"Ollama error: {error}")
        content = data.get("response", "") or ""
        if content:
            yield content

    @staticmethod
    async def list_models() -> list[str]:
        """Return names of locally available Ollama models."""
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(_OLLAMA_TAGS_URL)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
