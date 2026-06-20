from __future__ import annotations

from ._openai_compat import OpenAICompatibleProvider

_GITHUB_BASE_URL = "https://models.inference.ai.azure.com"


class GitHubModelsProvider(OpenAICompatibleProvider):
    """GitHub Models provider — free tier using a GitHub PAT."""

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=_GITHUB_BASE_URL)
