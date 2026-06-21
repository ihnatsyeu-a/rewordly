from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class Provider(str, Enum):
    GITHUB = "github"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"

    def next(self) -> "Provider":
        members = list(Provider)
        return members[(members.index(self) + 1) % len(members)]


class Tone(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"

    def next(self) -> "Tone":
        members = list(Tone)
        return members[(members.index(self) + 1) % len(members)]


_DEFAULT_MODELS: dict[Provider, str] = {
    Provider.GITHUB: "gpt-4o-mini",
    Provider.OPENAI: "gpt-4o-mini",
    Provider.GEMINI: "gemini-2.5-flash",
    Provider.OLLAMA: "",
}


_PROVIDER_ENV_VARS: dict[Provider, str | None] = {
    Provider.GITHUB: "GITHUB_TOKEN",
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.GEMINI: "GEMINI_API_KEY",
    Provider.OLLAMA: None,  # no key required
}


def available_providers() -> list[Provider]:
    """Return providers that have credentials configured (or require none)."""
    return [
        p for p in Provider
        if _PROVIDER_ENV_VARS[p] is None or bool(os.getenv(_PROVIDER_ENV_VARS[p], ""))
    ]


@dataclass
class Config:
    provider: Provider = field(
        default_factory=lambda: Provider(os.getenv("PROVIDER", "ollama").lower())
    )
    tone: Tone = field(
        default_factory=lambda: Tone(os.getenv("DEFAULT_TONE", "formal").lower())
    )
    model: str = ""
    min_input_chars: int = field(
        default_factory=lambda: int(os.getenv("MIN_INPUT_CHARS", "15"))
    )
    max_input_chars: int = field(
        default_factory=lambda: int(os.getenv("MAX_INPUT_CHARS", "2000"))
    )
    debounce_delay: float = field(
        default_factory=lambda: float(os.getenv("DEBOUNCE_DELAY", "1.2"))
    )

    def __post_init__(self) -> None:
        if not self.model:
            self.model = os.getenv("DEFAULT_MODEL", "") or _DEFAULT_MODELS[self.provider]

    def api_key(self) -> str:
        if self.provider == Provider.OLLAMA:
            return ""
        mapping = {
            Provider.GITHUB: "GITHUB_TOKEN",
            Provider.OPENAI: "OPENAI_API_KEY",
            Provider.GEMINI: "GEMINI_API_KEY",
        }
        key = os.getenv(mapping[self.provider], "")
        if not key:
            env_var = mapping[self.provider]
            raise ValueError(
                f"Missing credential for provider '{self.provider.value}'. "
                f"Set {env_var} in your .env file or environment."
            )
        return key


_config: Config | None = None


def get_config(
    provider: Provider | None = None,
    model: str = "",
    tone: Tone | None = None,
) -> Config:
    global _config
    if _config is None or provider is not None or model or tone is not None:
        cfg = Config(
            provider=provider or Provider(os.getenv("PROVIDER", "ollama").lower()),
            tone=tone or Tone(os.getenv("DEFAULT_TONE", "formal").lower()),
            model=model,
        )
        if _config is None:
            _config = cfg
        return cfg
    return _config
