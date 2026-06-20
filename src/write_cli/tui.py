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
MAX_ALTERNATIVES = 3
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _parse_retry_seconds(error_str: str) -> int | None:
    """Extract retry-after seconds from an API error message."""
    import re
    match = re.search(r"retry[^\d]*(\d+)", error_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


class InputTextArea(TextArea):
    """Left-panel input TextArea that passes Ctrl+Y up to the app."""

    def on_key(self, event) -> None:
        if event.key == "ctrl+y":
            self.app.action_accept()
            event.prevent_default()
            event.stop()


class SuggestionTextArea(TextArea):
    """Read-only TextArea that copies selections to the system clipboard on Ctrl+C."""

    def on_key(self, event) -> None:
        if event.key == "ctrl+y":
            # Let the app-level binding handle Copy All regardless of focus.
            self.app.action_accept()
            event.prevent_default()
            event.stop()
            return
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


def _build_diff_highlights(
    original: str, revised: str
) -> tuple[str, dict[int, list[tuple[int, int, str]]]]:
    """Return (revised_text, highlights) where highlights marks added word ranges green.

    highlights is dict[line_index -> list[(start_col, end_col, highlight_name)]].
    """
    import re
    import difflib
    from collections import defaultdict

    orig_tokens = re.findall(r"\S+|\s+", original)
    rev_tokens = re.findall(r"\S+|\s+", revised)

    # Build cumulative char offsets for each token in revised
    rev_offsets: list[int] = []
    pos = 0
    for t in rev_tokens:
        rev_offsets.append(pos)
        pos += len(t)
    rev_offsets.append(pos)  # sentinel

    rev_lines = revised.split("\n")

    def offset_to_line_col(offset: int) -> tuple[int, int]:
        cumulative = 0
        for line_idx, line in enumerate(rev_lines):
            line_end = cumulative + len(line)
            if offset <= line_end:
                return line_idx, offset - cumulative
            cumulative = line_end + 1  # +1 for \n
        last = len(rev_lines) - 1
        return last, len(rev_lines[last])

    highlights: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
    matcher = difflib.SequenceMatcher(None, orig_tokens, rev_tokens, autojunk=False)

    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            start_char = rev_offsets[j1]
            end_char = rev_offsets[j2]
            s_line, s_col = offset_to_line_col(start_char)
            e_line, e_col = offset_to_line_col(end_char)
            if s_line == e_line:
                highlights[s_line].append((s_col, e_col, "diff.added"))
            else:
                highlights[s_line].append((s_col, len(rev_lines[s_line]), "diff.added"))
                for mid in range(s_line + 1, e_line):
                    highlights[mid].append((0, len(rev_lines[mid]), "diff.added"))
                highlights[e_line].append((0, e_col, "diff.added"))

    return revised, dict(highlights)


class DiffTextArea(SuggestionTextArea):
    """Read-only TextArea that shows the suggestion with added-word highlights in green."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._copy_debounce: asyncio.TimerHandle | None = None

    def on_mount(self) -> None:
        from rich.style import Style
        try:
            self._theme.syntax_styles["diff.added"] = Style(color="green", bold=True)
        except Exception:
            pass

    def on_text_area_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        if self._copy_debounce is not None:
            self._copy_debounce.cancel()
            self._copy_debounce = None
        if self.selected_text:
            loop = asyncio.get_event_loop()
            self._copy_debounce = loop.call_later(0.4, self._do_copy)

    def _do_copy(self) -> None:
        self._copy_debounce = None
        text = self.selected_text
        if not text:
            return
        try:
            import pyperclip
            pyperclip.copy(text)
            self.app.notify("📋 Copied!", timeout=1.5)
        except Exception:
            self.app.notify("⚠ Clipboard not available.", severity="warning", timeout=2)

    def load_diff(self, original: str, revised: str) -> None:
        from collections import defaultdict
        text, hl = _build_diff_highlights(original, revised)
        self.load_text(text)
        self._highlights = defaultdict(list, hl)
        self.refresh()


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
    #right-panel-wrap {
        width: 1fr;
        height: 1fr;
        border: solid $primary;
    }
    #loading {
        dock: top;
        height: 1;
        padding: 0 0;
        color: $accent;
        display: none;
    }
    #diff-panel {
        width: 1fr;
        height: 1fr;
        border: none;
        padding: 0;
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
    #alt-counter {
        color: $accent;
        margin: 0 2;
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
    #toolbar {
        height: 1;
        background: $surface;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }
    """

    BINDINGS = [
        Binding("ctrl+t", "cycle_tone", "Tone", show=True, priority=True),
        Binding("ctrl+r", "cycle_mode", "Mode", show=True, priority=True),
        Binding("ctrl+n", "next_alt", "Next alt", show=False, priority=True),
        Binding("ctrl+p", "prev_alt", "Prev alt", show=False, priority=True),
        Binding("ctrl+y", "accept", "Copy all", show=True, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
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
        # Diff feature
        self._last_input_text: str = ""    # original input used for current suggestion
        # Alternatives feature
        self._alternatives: list[str] = []
        self._alt_index: int = 0
        # Spinner
        self._spinner_frame: int = 0
        self._spinner_timer = None

    def _active_mode(self) -> str:
        return MODES[self._mode_index]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield self._build_toolbar()
        with Horizontal(id="panels"):
            with Vertical(id="left-panel"):
                yield InputTextArea(id="input-area")
            with Vertical(id="right-panel-wrap"):
                yield Label("", id="loading")
                yield DiffTextArea("", id="diff-panel", read_only=True)
        with Horizontal(id="footer-bar"):
            yield Label("^T", classes="footer-hint-key")
            yield Label("Tone", classes="footer-hint")
            yield Label("^R", classes="footer-hint-key")
            yield Label("Mode", classes="footer-hint")
            yield Label("^N/^P", classes="footer-hint-key")
            yield Label("Alt", classes="footer-hint")
            yield Label("", id="alt-counter")
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

    def _update_diff_panel(self) -> None:
        diff = self.query_one("#diff-panel", DiffTextArea)
        if self._last_input_text and self._suggestion:
            diff.load_diff(self._last_input_text, self._suggestion)
        else:
            diff.load_text("No diff yet — generate a suggestion first.")

    def action_next_alt(self) -> None:
        if self._generating:
            return
        if self._alt_index < len(self._alternatives) - 1:
            self._display_alternative(self._alt_index + 1)
        elif len(self._alternatives) < MAX_ALTERNATIVES and self._last_input_text:
            self._run_alternative(self._last_input_text)
        else:
            self.notify(f"Max {MAX_ALTERNATIVES} alternatives reached.", timeout=1.5)

    def action_prev_alt(self) -> None:
        if self._alt_index > 0:
            self._display_alternative(self._alt_index - 1)

    def _display_alternative(self, idx: int) -> None:
        self._alt_index = idx
        suggestion = self._alternatives[idx]
        self._suggestion = suggestion
        self._update_diff_panel()
        self._update_alt_counter()
        self._set_copy_btn(True)

    def _update_alt_counter(self) -> None:
        counter = self.query_one("#alt-counter", Label)
        if len(self._alternatives) <= 1:
            counter.update("")
        else:
            counter.update(f"{self._alt_index + 1}/{len(self._alternatives)}")

    @work(exclusive=False)
    async def _run_alternative(self, text: str) -> None:
        self._generating = True
        self._set_copy_btn(False)
        self._start_spinner()
        language = await asyncio.get_event_loop().run_in_executor(
            None, detect_language, text
        )
        accumulated = ""
        try:
            gen: AsyncIterator[str] = self._provider.stream_suggestion(
                text=text,
                mode="alternative",
                tone=self._config.tone.value,
                language=language,
                model=self._config.model,
            )
            async for token in gen:
                accumulated += token
        except Exception as exc:
            self.notify(f"Alt generation failed: {str(exc)[:80]}", severity="error", timeout=4)
            self._generating = False
            self._stop_spinner()
            self._set_copy_btn(bool(self._suggestion))
            return
        if accumulated:
            self._alternatives.append(accumulated)
            self._display_alternative(len(self._alternatives) - 1)
        self._stop_spinner()
        self._generating = False

    def _cache_key(self, text: str) -> tuple[str, str, str, str]:
        return (text, self._active_mode(), self._config.tone.value, self._config.model)

    @on(TextArea.Changed, "#input-area")
    def on_input_changed(self, event: TextArea.Changed) -> None:
        """Debounce: schedule auto-generation after typing stops."""
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
        text = event.text_area.text.strip()
        if not text:
            self.query_one("#diff-panel", DiffTextArea).load_text("")
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
            self.query_one("#diff-panel", DiffTextArea).load_text(
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
            self._suggestion = self._cache[key]
            self._last_input_text = text
            self._update_diff_panel()
            self._set_copy_btn(True)
            return
        self._run_generation(text)

    def _set_copy_btn(self, enabled: bool) -> None:
        for wid in ("copy-hint-key", "copy-hint-label"):
            self.query_one(f"#{wid}", Label).set_class(not enabled, "is-disabled")

    def _start_spinner(self) -> None:
        self._spinner_frame = 0
        lbl = self.query_one("#loading", Label)
        lbl.display = True
        lbl.update(f"{SPINNER_FRAMES[0]} Generating")
        self._spinner_timer = self.set_interval(0.1, self._tick_spinner)

    def _stop_spinner(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.query_one("#loading", Label).display = False

    def _tick_spinner(self) -> None:
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        self.query_one("#loading", Label).update(
            f"{SPINNER_FRAMES[self._spinner_frame]} Generating"
        )

    @work(exclusive=True)
    async def _run_generation(self, text: str) -> None:
        self._generating = True
        self._set_copy_btn(False)
        self._start_spinner()
        diff_panel = self.query_one("#diff-panel", DiffTextArea)

        # Input truncation
        truncated = False
        send_text = text
        if len(text) > self._config.max_input_chars:
            send_text = text[: self._config.max_input_chars]
            truncated = True

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
                diff_panel.load_text(accumulated)

        except Exception as exc:
            await self._handle_api_error(exc, send_text, diff_panel)
            self._stop_spinner()
            self._generating = False
            return

        if truncated:
            accumulated += f"\n\n[Input was truncated to {self._config.max_input_chars} characters]"

        self._suggestion = accumulated
        self._last_input_text = text
        self._update_diff_panel()
        # Reset alternatives to just this first result
        self._alternatives = [accumulated]
        self._alt_index = 0
        self._update_alt_counter()
        # Store in cache (evict oldest if over 20 entries)
        key = self._cache_key(text)
        if len(self._cache) >= 20:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = accumulated
        self._last_generated_key = key

        self._stop_spinner()
        self._set_copy_btn(True)
        self._generating = False

    async def _handle_api_error(self, exc: Exception, text: str, panel: DiffTextArea) -> None:
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
                    "• Wait a minute and press Ctrl+R to retry\n"
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
                "Check your internet connection and press Ctrl+R to retry."
            )
        else:
            panel.load_text(
                f"⚠ Unexpected error\n\n{exc_str[:300]}\n\nPress Ctrl+R to retry."
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
