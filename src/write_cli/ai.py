from __future__ import annotations

from .config import Config, Provider
from .providers.base import AIProvider
from .providers.gemini import GeminiProvider
from .providers.github import GitHubModelsProvider
from .providers.openai_provider import OpenAIProvider


def create_provider(config: Config) -> AIProvider:
    """Instantiate the AI provider specified in *config*."""
    api_key = config.api_key()
    match config.provider:
        case Provider.GITHUB:
            return GitHubModelsProvider(api_key)
        case Provider.OPENAI:
            return OpenAIProvider(api_key)
        case Provider.GEMINI:
            return GeminiProvider(api_key)
        case _:
            raise ValueError(f"Unknown provider: {config.provider}")
