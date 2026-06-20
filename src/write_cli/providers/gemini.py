from __future__ import annotations

from ._openai_compat import OpenAICompatibleProvider

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini provider — free tier via AI Studio API key."""

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=_GEMINI_BASE_URL)
