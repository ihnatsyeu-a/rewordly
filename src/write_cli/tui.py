from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Header,
    Label,
    TextArea,
)

try:
    import langdetect

    def detect_language(text: str) -> str:
        try:
            code = langdetect.detect(text)
            return _LANG_CODES.get(code, "English")
        except Exception:
            return "English"

except ImportError:
    def detect_language(text: str) -> str:  # type: ignore[misc]
        return "English"


_LANG_CODES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "zh-cn": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "tr": "Turkish",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "nb": "Norwegian",
    "cs": "Czech",
    "ro": "Romanian",
}

MODES = ["rephrase", "grammar"]
MODE_LABELS = {"rephrase": "Rephrase", "grammar": "Grammar"}


def _parse_retry_seconds(error_str: str) -> int | None:
    """Extract retry-after seconds from an API error message."""
    import re
    match = re.search(r"retry[^\d]*(\d+)", error_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


class SuggestionTextArea(TextArea):
    """Read-only TextArea that copies selections to the system clipboard on Ctrl+C."""

    def on_key(self, event) -> None:
        if event.key in ("ctrl+c", "meta+c"):
            text = self.selected_text
            if text:
                try:
                    import pyperclip
                    pyperclip.copy(text)
                    self.app.notify("📋 Copied to clipboard!", timeout=1.5)
                except Exception:
                    self.app.notify("⚠ Clipboard not available.", severity="warning", timeout=2)
                event.prevent_default()
                event.stop()


class StatusBar(Label):
    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 2;
    }
    """


class WriteApp(App):
    """Rewordly TUI application."""

    TITLE = "Rewordly"
    CSS = """
    Screen {
        layout: vertical;
    }
    #panels {
        height: 1fr;
        layout: horizontal;
    }
    #left-panel {
        width: 1fr;
        height: 1fr;
        border: solid $accent;
        padding: 0;
    }
    #left-panel TextArea {
        height: 1fr;
        border: none;
    }
    #right-panel {
        width: 1fr;
        height: 1fr;
        border: none;
    }
    #right-panel-wrap {
        width: 1fr;
        height: 1fr;
        border: solid $primary;
    }
    #footer-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }
    .footer-hint {
        margin: 0 1;
        color: $text-muted;
    }
    .footer-hint-key {
        color: $text;
        background: $surface-lighten-2;
        padding: 0 1;
    }
    #copy-hint-key.is-disabled, #copy-hint-label.is-disabled {
        color: $text-disabled;
        background: transparent;
    }
    .toolbar-label {
        margin: 0 1;
        color: $text-muted;
        padding: 0 0;
    }
    .tone-btn, .mode-btn, .provider-btn {
        min-width: 0;
        height: 1;
        margin: 0 0;
        padding: 0 1;
        border: none;
        background: $surface-lighten-2;
        color: $text-muted;
    }
    .tone-btn:hover, .mode-btn:hover, .provider-btn:hover {
        background: $surface-lighten-3;
        color: $text;
    }
    .tone-btn.is-active, .mode-btn.is-active, .provider-btn.is-active {
        background: $primary;
        color: $background;
    }
    #generate-btn {
        min-width: 12;
        height: 1;
        margin: 0 1;
        border: none;
    }
    #toolbar {
        height: 1;
        background: $surface;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }
    """

    BINDINGS = [
        Binding("ctrl+g", "generate", "Generate", show=True),
        Binding("ctrl+t", "cycle_tone", "Tone", show=True),
        Binding("ctrl+r", "cycle_mode", "Mode", show=True),
        Binding("ctrl+y", "accept", "Copy all", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, provider, config) -> None:  # type: ignore[type-arg]
        super().__init__()
        self._provider = provider
        self._config = config
        self._suggestion = ""
        self._generating = False
        self._mode_index = 0
        self._debounce_handle: asyncio.TimerHandle | None = None
        # Cache: (text, mode, tone, model) -> suggestion
        self._cache: dict[tuple[str, str, str, str], str] = {}
        # Track last successfully generated key to avoid re-requesting unchanged input
        self._last_generated_key: tuple[str, str, str, str] | None = None
        # Track text at last debounce trigger to detect trivial changes
        self._last_triggered_text: str = ""

    def _active_mode(self) -> str:
        return MODES[self._mode_index]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield self._build_toolbar()
        with Horizontal(id="panels"):
            with Vertical(id="left-panel"):
                yield TextArea(id="input-area")
            with Vertical(id="right-panel-wrap"):
                yield SuggestionTextArea("", id="right-panel", read_only=True)
        with Horizontal(id="footer-bar"):
            yield Label("^G", classes="footer-hint-key")
            yield Label("Generate", classes="footer-hint")
            yield Label("^T", classes="footer-hint-key")
            yield Label("Tone", classes="footer-hint")
            yield Label("^R", classes="footer-hint-key")
            yield Label("Mode", classes="footer-hint")
            yield Label("^Y", classes="footer-hint-key", id="copy-hint-key")
            yield Label("Copy all", classes="footer-hint", id="copy-hint-label")
            yield Label("^Q", classes="footer-hint-key")
            yield Label("Quit", classes="footer-hint")

    def _build_toolbar(self) -> Horizontal:
        return Horizontal(id="toolbar")

    def on_mount(self) -> None:
        from .config import Tone, Provider
        self.sub_title = f"{self._config.provider.value}  /  {self._config.model}"
        toolbar = self.query_one("#toolbar", Horizontal)
        toolbar.mount(
            Label("Provider:", classes="toolbar-label"),
            *[Button(p.value.capitalize(), id=f"provider-{p.value}", classes="provider-btn")
              for p in Provider],
            Label("  ", classes="toolbar-label"),
            Label("Tone:", classes="toolbar-label"),
            *[Button(t.value.capitalize(), id=f"tone-{t.value}", classes="tone-btn")
              for t in Tone],
            Label("  ", classes="toolbar-label"),
            Label("Mode:", classes="toolbar-label"),
            *[Button(m.capitalize(), id=f"mode-{m}", classes="mode-btn")
              for m in MODES],
            Label("  ", classes="toolbar-label"),
            Button("⚡ Generate", id="generate-btn", variant="primary"),
        )
        self._refresh_toolbar_states()
        self.query_one("#input-area", TextArea).focus()

    def _refresh_toolbar_states(self) -> None:
        """Update active/inactive CSS classes on toolbar buttons without remounting."""
        from .config import Tone, Provider
        for p in Provider:
            btn = self.query_one(f"#provider-{p.value}", Button)
            btn.set_class(p == self._config.provider, "is-active")
        for t in Tone:
            btn = self.query_one(f"#tone-{t.value}", Button)
            btn.set_class(t == self._config.tone, "is-active")
        for m in MODES:
            btn = self.query_one(f"#mode-{m}", Button)
            btn.set_class(m == self._active_mode(), "is-active")

    def _update_toolbar(self) -> None:
        self._refresh_toolbar_states()

    def _switch_provider(self, provider_value: str) -> None:
        from .ai import create_provider
        from .config import Provider, get_config
        try:
            new_provider_enum = Provider(provider_value)
            if new_provider_enum == self._config.provider:
                return
            # Build a temporary config to validate credentials
            new_cfg = get_config(
                provider=new_provider_enum,
                model="",
                tone=self._config.tone,
            )
            new_provider_instance = create_provider(new_cfg)
        except ValueError as exc:
            self.notify(str(exc), severity="error", timeout=5)
            return
        # Switch over
        self._provider = new_provider_instance
        self._config.provider = new_provider_enum
        self._config.model = new_cfg.model
        # Clear cache — different provider may give different results
        self._cache.clear()
        self._last_generated_key = None
        self.sub_title = f"{self._config.provider.value}  /  {self._config.model}"
        self._refresh_toolbar_states()
        self.notify(f"Provider: {provider_value}  /  {self._config.model}", timeout=2)
        self._trigger_auto_generate()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("provider-"):
            self._switch_provider(btn_id[len("provider-"):])
        elif btn_id.startswith("tone-"):
            from .config import Tone
            self._config.tone = Tone(btn_id[len("tone-"):])
            self._refresh_toolbar_states()
            self.notify(f"Tone: {self._config.tone.value}", timeout=1.5)
            self._trigger_auto_generate()
        elif btn_id.startswith("mode-"):
            mode = btn_id[len("mode-"):]
            self._mode_index = MODES.index(mode)
            self._refresh_toolbar_states()
            self.notify(f"Mode: {mode}", timeout=1.5)
            self._trigger_auto_generate()
        elif btn_id == "generate-btn":
            self.action_generate()
        event.stop()

    def action_cycle_tone(self) -> None:
        self._config.tone = self._config.tone.next()
        self._update_toolbar()
        self.notify(f"Tone: {self._config.tone.value}", timeout=1.5)
        self._trigger_auto_generate()

    def action_cycle_mode(self) -> None:
        self._mode_index = (self._mode_index + 1) % len(MODES)
        self._update_toolbar()
        self.notify(f"Mode: {self._active_mode()}", timeout=1.5)
        self._trigger_auto_generate()

    def _cache_key(self, text: str) -> tuple[str, str, str, str]:
        return (text, self._active_mode(), self._config.tone.value, self._config.model)

    @on(TextArea.Changed, "#input-area")
    def on_input_changed(self, event: TextArea.Changed) -> None:
        """Debounce: schedule auto-generation after typing stops."""
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
        text = event.text_area.text.strip()
        if not text:
            self.query_one("#right-panel", SuggestionTextArea).load_text("")
            self._last_triggered_text = ""
            return
        # Skip if trivial change (< 3 chars different from last trigger)
        if abs(len(text) - len(self._last_triggered_text)) < 3 and text != self._last_triggered_text:
            changed = sum(a != b for a, b in zip(text, self._last_triggered_text))
            if changed < 3 and abs(len(text) - len(self._last_triggered_text)) < 3:
                pass  # still schedule — just use longer delay implicitly
        loop = asyncio.get_event_loop()
        self._debounce_handle = loop.call_later(
            self._config.debounce_delay, self._trigger_auto_generate
        )

    def _trigger_auto_generate(self) -> None:
        self._debounce_handle = None
        text = self.query_one("#input-area", TextArea).text.strip()
        if not text:
            return
        # Min chars guard
        if len(text) < self._config.min_input_chars:
            self.query_one("#right-panel", SuggestionTextArea).load_text(
                f"Type at least {self._config.min_input_chars} characters to get a suggestion…"
            )
            return
        # Skip if nothing changed since last successful generation
        key = self._cache_key(text)
        if key == self._last_generated_key:
            return
        self._last_triggered_text = text
        # Serve from cache if available
        if key in self._cache:
            panel = self.query_one("#right-panel", SuggestionTextArea)
            panel.load_text(self._cache[key])
            self._suggestion = self._cache[key]
            self._set_copy_btn(True)
            return
        self._run_generation(text)

    def action_generate(self) -> None:
        """Force-generate, bypassing debounce and cache."""
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
            self._debounce_handle = None
        text = self.query_one("#input-area", TextArea).text.strip()
        if not text:
            self.notify("Please enter some text first.", severity="warning")
            return
        # Invalidate cache for current key so force-generate always calls API
        self._cache.pop(self._cache_key(text), None)
        self._last_generated_key = None
        self._run_generation(text)

    def _set_copy_btn(self, enabled: bool) -> None:
        for wid in ("copy-hint-key", "copy-hint-label"):
            self.query_one(f"#{wid}", Label).set_class(not enabled, "is-disabled")

    @work(exclusive=True)
    async def _run_generation(self, text: str) -> None:
        self._generating = True
        self._set_copy_btn(False)
        panel = self.query_one("#right-panel", SuggestionTextArea)

        # Input truncation
        truncated = False
        send_text = text
        if len(text) > self._config.max_input_chars:
            send_text = text[: self._config.max_input_chars]
            truncated = True

        panel.load_text("Generating…")

        language = await asyncio.get_event_loop().run_in_executor(
            None, detect_language, send_text
        )

        accumulated = ""
        try:
            gen: AsyncIterator[str] = self._provider.stream_suggestion(
                text=send_text,
                mode=self._active_mode(),
                tone=self._config.tone.value,
                language=language,
                model=self._config.model,
            )
            async for token in gen:
                accumulated += token
                panel.load_text(accumulated)

        except Exception as exc:
            await self._handle_api_error(exc, send_text, panel)
            self._generating = False
            return

        if truncated:
            accumulated += f"\n\n[Input was truncated to {self._config.max_input_chars} characters]"

        self._suggestion = accumulated
        # Store in cache (evict oldest if over 20 entries)
        key = self._cache_key(text)
        if len(self._cache) >= 20:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = accumulated
        self._last_generated_key = key

        panel.load_text(accumulated)
        self._set_copy_btn(True)
        self._generating = False

    async def _handle_api_error(self, exc: Exception, text: str, panel: SuggestionTextArea) -> None:
        """Classify API errors and show friendly messages; auto-retry on rate limit."""
        exc_str = str(exc)
        code = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )

        retry_after = _parse_retry_seconds(exc_str)

        if code == 429 or "429" in exc_str or "rate" in exc_str.lower() or "quota" in exc_str.lower():
            if retry_after and retry_after <= 60:
                for remaining in range(retry_after, 0, -1):
                    panel.load_text(
                        f"⏳ Rate limit reached — retrying in {remaining}s…\n\n"
                        f"The free tier has a request quota. "
                        f"Consider upgrading or switching providers."
                    )
                    await asyncio.sleep(1)
                panel.load_text("Retrying…")
                self._trigger_auto_generate()
            else:
                panel.load_text(
                    "⏳ Rate limit reached\n\n"
                    "The free tier quota is exhausted.\n"
                    "• Wait a minute and press Ctrl+G to retry\n"
                    "• Or switch provider: --provider openai / --provider github"
                )
        elif code == 401 or "401" in exc_str or "unauthorized" in exc_str.lower() or "api key" in exc_str.lower():
            panel.load_text(
                "🔑 Authentication failed\n\n"
                "Your API key appears to be invalid or missing.\n"
                "Check your .env file and ensure the correct key is set."
            )
        elif code == 404 or "404" in exc_str or "not found" in exc_str.lower():
            panel.load_text(
                f"🔍 Model not found\n\n"
                f"Model '{self._config.model}' is not available.\n"
                "Try --model gemini-2.5-flash or check provider docs."
            )
        elif "connection" in exc_str.lower() or "network" in exc_str.lower() or "timeout" in exc_str.lower():
            panel.load_text(
                "🌐 Network error\n\n"
                "Could not reach the AI provider.\n"
                "Check your internet connection and press Ctrl+G to retry."
            )
        else:
            panel.load_text(
                f"⚠ Unexpected error\n\n{exc_str[:300]}\n\nPress Ctrl+G to retry."
            )

    def action_accept(self) -> None:
        if not self._suggestion:
            self.notify("No suggestion to accept yet.", severity="warning")
            return
        try:
            import pyperclip
            pyperclip.copy(self._suggestion)
            self.notify("✅ Suggestion copied to clipboard!", timeout=2)
        except Exception:
            self.query_one("#input-area", TextArea).load_text(self._suggestion)
            self.notify("✅ Suggestion moved to input (clipboard unavailable).", timeout=2)

    def action_quit(self) -> None:
        self.exit()
