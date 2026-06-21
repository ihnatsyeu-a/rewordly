from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from .base import AIProvider

_SYSTEM_PROMPT = (
    "You are an expert writing assistant. "
    "When given a text, return ONLY the improved version — no explanations, "
    "no preamble, no quotation marks around the output."
)

_MODE_INSTRUCTIONS: dict[str, str] = {
    "rephrase": (
        "Rephrase the following {language} text in a {tone} tone. "
        "Make it clearer and more natural while preserving the original meaning."
    ),
    "grammar": (
        "Correct all grammar, spelling, and punctuation errors in the following {language} text. "
        "Preserve the author's voice, style, and meaning exactly — do not rephrase or change the tone."
    ),
    "alternative": (
        "Rephrase the following {language} text in a {tone} tone, but produce a version that is "
        "distinctly different in wording and sentence structure from any previous suggestion. "
        "Preserve the original meaning."
    ),
}


def _build_prompt(text: str, mode: str, tone: str, language: str) -> str:
    template = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["rephrase"])
    instruction = template.format(language=language, tone=tone)
    return f"{instruction}\n\nText:\n{text}"


class OpenAICompatibleProvider(AIProvider):
    """Shared implementation for all OpenAI-API-compatible providers."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    async def stream_suggestion(
        self,
        text: str,
        mode: str,
        tone: str,
        language: str,
        model: str,
    ) -> AsyncIterator[str]:
        prompt = _build_prompt(text, mode, tone, language)
        stream = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
