from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from blogbook.models import PreflightSummary
from blogbook.pipeline import GenerationCancelled, create_book_from_file
from blogbook.translate import NoopTranslator, OpenAITranslator, TranslationError

app = typer.Typer(
    no_args_is_help=True,
    help="Create small translated EPUB e-books from blog posts.",
)


@app.callback()
def main() -> None:
    """Create small translated EPUB e-books from blog posts."""


@app.command()
def create(
    urls_file: Path = typer.Argument(..., help="Text file with one blog post URL per line."),
    output: Path = typer.Option(Path("book.epub"), "--output", "-o", help="Output EPUB path."),
    title: Optional[str] = typer.Option(None, "--title", help="Override book title."),
    translate: bool = typer.Option(
        True,
        "--translate/--no-translate",
        help="Translate article text into Czech.",
    ),
    model: str = typer.Option("gpt-4.1-mini", "--model", help="OpenAI model for translation."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Start generation without asking for confirmation after the preflight summary.",
    ),
) -> None:
    translator = OpenAITranslator(model=model) if translate else NoopTranslator()
    phase_started: dict[str, float] = {}

    def show_progress(phase: str, current: int, total: int, detail: str) -> None:
        eta = ""
        if current > 0 and phase in {"check", "translate"}:
            phase_started.setdefault(phase, time.monotonic())
            elapsed = time.monotonic() - phase_started[phase]
            remaining = max(total - current, 0)
            eta_seconds = (elapsed / current) * remaining
            eta = f" | odhad zbývá {_format_duration(eta_seconds)}"
        labels = {
            "check": "Kontrola",
            "translate": "Překlad",
            "skip": "Vynecháno",
        }
        typer.echo(f"[{labels.get(phase, phase)} {current}/{total}] {detail}{eta}")

    def confirm_generation(summary: PreflightSummary) -> bool:
        _print_summary(summary, translate)
        return yes or typer.confirm("Pokračovat v generování?", default=False)

    try:
        result = create_book_from_file(
            urls_file=urls_file,
            output_path=output,
            translator=translator,
            title=title,
            confirm=confirm_generation,
            progress=show_progress,
        )
    except GenerationCancelled as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=0) from exc
    except (OSError, RuntimeError, TranslationError, ValueError) as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created EPUB: {result}")


def _print_summary(summary: PreflightSummary, translate: bool) -> None:
    typer.echo("\nSouhrn před generováním")
    typer.echo(f"  URL celkem:       {summary.total_urls}")
    typer.secho(f"  Použitelné:       {summary.usable_urls}", fg=typer.colors.GREEN)
    color = typer.colors.YELLOW if summary.skipped_urls else None
    typer.secho(f"  Vynechané:        {summary.skipped_urls}", fg=color)
    if translate:
        typer.echo(f"  Odhad tokenů:     ~{summary.estimated_tokens:,}".replace(",", " "))
        typer.echo("  (vstup + výstup; skutečná spotřeba se může lišit)")

    skipped = [item for item in summary.items if not item.usable]
    if skipped:
        typer.echo("\nVynechané stránky:")
        for item in skipped:
            typer.echo(f"  - {item.url}: {item.reason}")
    typer.echo()


def _format_duration(seconds: float) -> str:
    rounded = max(0, round(seconds))
    minutes, seconds_part = divmod(rounded, 60)
    if minutes:
        return f"{minutes} min {seconds_part} s"
    return f"{seconds_part} s"


if __name__ == "__main__":
    app()
