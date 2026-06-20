from __future__ import annotations

from typing import Optional

import typer

from .ai import create_provider
from .config import Provider, Tone, get_config

app = typer.Typer(
    name="rewordly",
    help="✍️  Rewordly — improve your writing with AI.",
    add_completion=False,
)


@app.command()
def main(
    text: Optional[str] = typer.Argument(
        None,
        help="Text to improve. If omitted, launches the interactive TUI.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        "-p",
        help="AI provider to use: github | openai | gemini. Overrides PROVIDER env var.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model name (e.g. gpt-4o, gemini-1.5-pro). Overrides DEFAULT_MODEL env var.",
    ),
    tone: Optional[str] = typer.Option(
        None,
        "--tone",
        "-t",
        help="Writing tone: formal | casual | professional | friendly.",
    ),
    mode: str = typer.Option(
        "rephrase",
        "--mode",
        "-m",
        help="Improvement mode: rephrase (rewrites with tone) | grammar (fixes errors only).",
    ),
) -> None:
    """Launch the interactive TUI writing assistant."""
    try:
        prov = Provider(provider.lower()) if provider else None
        ton = Tone(tone.lower()) if tone else None
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    try:
        config = get_config(provider=prov, model=model or "", tone=ton)
        ai_provider = create_provider(config)
    except ValueError as exc:
        typer.echo(f"❌  {exc}", err=True)
        _print_setup_hint(config.provider if "config" in dir() else None)
        raise typer.Exit(1)

    if text:
        # Non-interactive: print suggestion to stdout
        import asyncio

        async def _run() -> None:
            try:
                from langdetect import detect  # type: ignore[import]
                from .tui import _LANG_CODES, detect_language  # noqa: F401
                lang_code = detect(text)
                language = _LANG_CODES.get(lang_code, "English")
            except Exception:
                language = "English"

            async for token in ai_provider.stream_suggestion(
                text=text,
                mode=mode,
                tone=config.tone.value,
                language=language,
                model=config.model,
            ):
                typer.echo(token, nl=False)
            typer.echo()

        asyncio.run(_run())
    else:
        from .tui import WriteApp
        app_instance = WriteApp(provider=ai_provider, config=config)
        app_instance.run()


def _print_setup_hint(provider: Optional[Provider]) -> None:
    hints = {
        Provider.GITHUB: "Set GITHUB_TOKEN in your .env file.\nGet a free PAT at: https://github.com/settings/tokens",
        Provider.OPENAI: "Set OPENAI_API_KEY in your .env file.\nGet an API key at: https://platform.openai.com/api-keys",
        Provider.GEMINI: "Set GEMINI_API_KEY in your .env file.\nGet a free key at: https://aistudio.google.com/app/apikey",
    }
    if provider and provider in hints:
        typer.echo(f"\n💡  Setup hint:\n{hints[provider]}", err=True)
    else:
        typer.echo("\n💡  Copy .env.example to .env and fill in your credentials.", err=True)
