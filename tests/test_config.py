"""Tests for write_cli.config."""
from __future__ import annotations

import os
import importlib

import pytest

import write_cli.config as config_module
from write_cli.config import (
    Config,
    Provider,
    Tone,
    available_providers,
    get_config,
)


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


def test_provider_values():
    assert Provider.GITHUB.value == "github"
    assert Provider.OPENAI.value == "openai"
    assert Provider.GEMINI.value == "gemini"
    assert Provider.OLLAMA.value == "ollama"


def test_provider_from_string():
    assert Provider("github") is Provider.GITHUB
    assert Provider("ollama") is Provider.OLLAMA


def test_provider_next_cycles():
    members = list(Provider)
    for i, p in enumerate(members):
        assert p.next() is members[(i + 1) % len(members)]


def test_provider_next_wraps_around():
    last = list(Provider)[-1]
    assert last.next() is list(Provider)[0]


# ---------------------------------------------------------------------------
# Tone enum
# ---------------------------------------------------------------------------


def test_tone_values():
    assert Tone.FORMAL.value == "formal"
    assert Tone.CASUAL.value == "casual"
    assert Tone.PROFESSIONAL.value == "professional"
    assert Tone.FRIENDLY.value == "friendly"


def test_tone_next_cycles():
    members = list(Tone)
    for i, t in enumerate(members):
        assert t.next() is members[(i + 1) % len(members)]


def test_tone_next_wraps_around():
    last = list(Tone)[-1]
    assert last.next() is list(Tone)[0]


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("PROVIDER", raising=False)
    monkeypatch.delenv("DEFAULT_TONE", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    cfg = Config()
    assert cfg.provider == Provider.OLLAMA
    assert cfg.tone == Tone.FORMAL
    assert cfg.model == ""

def test_config_default_model_per_provider(monkeypatch):
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    assert Config(provider=Provider.GITHUB).model == "gpt-4o-mini"
    assert Config(provider=Provider.OPENAI).model == "gpt-4o-mini"
    assert Config(provider=Provider.GEMINI).model == "gemini-2.5-flash"
    assert Config(provider=Provider.OLLAMA).model == ""


def test_config_custom_model_overrides(monkeypatch):
    cfg = Config(provider=Provider.OLLAMA, model="gemma3:4b")
    assert cfg.model == "gemma3:4b"


def test_config_env_default_model(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "custom-model")
    cfg = Config(provider=Provider.OLLAMA, model="")
    assert cfg.model == "custom-model"
    monkeypatch.delenv("DEFAULT_MODEL")


def test_config_api_key_ollama():
    cfg = Config(provider=Provider.OLLAMA)
    assert cfg.api_key() == ""


def test_config_api_key_github(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
    cfg = Config(provider=Provider.GITHUB)
    assert cfg.api_key() == "ghp_test123"


def test_config_api_key_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = Config(provider=Provider.OPENAI)
    assert cfg.api_key() == "sk-test"


def test_config_api_key_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    cfg = Config(provider=Provider.GEMINI)
    assert cfg.api_key() == "AIza-test"


def test_config_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = Config(provider=Provider.GITHUB)
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        cfg.api_key()


def test_config_api_key_missing_openai_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = Config(provider=Provider.OPENAI)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        cfg.api_key()


def test_config_api_key_missing_gemini_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = Config(provider=Provider.GEMINI)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        cfg.api_key()


# ---------------------------------------------------------------------------
# available_providers()
# ---------------------------------------------------------------------------


def test_available_providers_always_includes_ollama(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    providers = available_providers()
    assert Provider.OLLAMA in providers


def test_available_providers_excludes_missing_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    providers = available_providers()
    assert Provider.OPENAI not in providers


def test_available_providers_includes_configured_keys(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-x")
    providers = available_providers()
    assert Provider.GITHUB in providers
    assert Provider.OPENAI in providers
    assert Provider.GEMINI in providers
    assert Provider.OLLAMA in providers


def test_available_providers_only_ollama_when_no_keys(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    providers = available_providers()
    assert providers == [Provider.OLLAMA]


# ---------------------------------------------------------------------------
# get_config()
# ---------------------------------------------------------------------------


def test_get_config_caches_instance(monkeypatch):
    monkeypatch.setattr(config_module, "_config", None)
    monkeypatch.delenv("PROVIDER", raising=False)
    cfg1 = get_config()
    cfg2 = get_config()
    assert cfg1 is cfg2


def test_get_config_respects_provider_override(monkeypatch):
    monkeypatch.setattr(config_module, "_config", None)
    cfg = get_config(provider=Provider.GEMINI)
    assert cfg.provider == Provider.GEMINI


def test_get_config_respects_tone_override(monkeypatch):
    monkeypatch.setattr(config_module, "_config", None)
    cfg = get_config(tone=Tone.CASUAL)
    assert cfg.tone == Tone.CASUAL
