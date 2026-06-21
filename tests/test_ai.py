"""Tests for write_cli.ai — provider factory."""
from __future__ import annotations

import pytest

from write_cli.config import Config, Provider, Tone
from write_cli.ai import create_provider
from write_cli.providers.github import GitHubModelsProvider
from write_cli.providers.openai_provider import OpenAIProvider
from write_cli.providers.gemini import GeminiProvider
from write_cli.providers.ollama import OllamaProvider


def _cfg(provider: Provider, **kwargs) -> Config:
    return Config(provider=provider, **kwargs)


def test_create_provider_ollama():
    cfg = _cfg(Provider.OLLAMA)
    provider = create_provider(cfg)
    assert isinstance(provider, OllamaProvider)


def test_create_provider_github(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    cfg = _cfg(Provider.GITHUB)
    provider = create_provider(cfg)
    assert isinstance(provider, GitHubModelsProvider)


def test_create_provider_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = _cfg(Provider.OPENAI)
    provider = create_provider(cfg)
    assert isinstance(provider, OpenAIProvider)


def test_create_provider_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    cfg = _cfg(Provider.GEMINI)
    provider = create_provider(cfg)
    assert isinstance(provider, GeminiProvider)


def test_create_provider_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = _cfg(Provider.GITHUB)
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        create_provider(cfg)


def test_create_provider_ollama_needs_no_key():
    """OllamaProvider must be created without any env var."""
    cfg = Config(provider=Provider.OLLAMA)
    # Should not raise even if all other provider keys are absent
    provider = create_provider(cfg)
    assert isinstance(provider, OllamaProvider)
