from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    @abstractmethod
    async def stream_suggestion(
        self,
        text: str,
        mode: str,
        tone: str,
        language: str,
        model: str,
    ) -> AsyncIterator[str]:
        """Stream writing suggestion tokens.

        Args:
            text: The input text to improve.
            mode: One of 'rephrase', 'grammar', 'tone'.
            tone: Target tone (formal/casual/professional/friendly).
            language: Detected language name (e.g. 'English', 'French').
            model: Model identifier to use.

        Yields:
            Text tokens as they stream from the API.
        """
        ...
