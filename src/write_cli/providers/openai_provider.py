from __future__ import annotations

from ._openai_compat import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    """OpenAI provider — pay-per-use via OPENAI_API_KEY."""

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=None)
