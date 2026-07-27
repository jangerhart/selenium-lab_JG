from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from pdfbook.extract import PdfExtractionError
from pdfbook.models import ExtractionResult
from pdfbook.pipeline import GenerationCancelled, translate_pdf
from pdfbook.translate import OpenAITranslator, TranslationError

app = typer.Typer(
    no_args_is_help=True,
    help="Translate text-based PDF books into clean Czech PDFs.",
)


@app.callback()
def main() -> None:
    """Translate text-based PDF books into clean Czech PDFs."""


@app.command()
def translate(
    input_pdf: Path = typer.Argument(..., help="Text-based source PDF."),
    output: Path = typer.Option(
        Path("output/pdf/translated-cs.pdf"),
        "--output",
        "-o",
        help="Translated PDF path.",
    ),
    title: Optional[str] = typer.Option(None, "--title", help="Optional Czech title page."),
    model: str = typer.Option("gpt-4.1-mini", "--model", help="OpenAI translation model."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation after analysis."),
) -> None:
    started = time.monotonic()

    def confirm(result: ExtractionResult) -> bool:
        typer.echo("\nAnalýza vstupního PDF")
        typer.echo(f"  Stránek:                 {result.page_count}")
        typer.echo(f"  Znaků k překladu:        {result.character_count:,}".replace(",", " "))
        typer.echo(f"  Odhad tokenů:            ~{result.estimated_tokens:,}".replace(",", " "))
        typer.echo(
            f"  Odstraněných záhlaví / zápatí: {len(result.removed_header_footer_lines)}"
        )
        typer.echo("  Odhad zahrnuje vstup i výstup a skutečná spotřeba se může lišit.\n")
        return yes or typer.confirm("Pokračovat v překladu?", default=False)

    def progress(current: int, total: int, detail: str) -> None:
        elapsed = time.monotonic() - started
        remaining = max(total - current, 0)
        eta = (elapsed / current) * remaining
        typer.echo(
            f"[Překlad {current}/{total}] {detail} | odhad zbývá {_duration(eta)}"
        )

    try:
        result = translate_pdf(
            input_path=input_pdf,
            output_path=output,
            translator=OpenAITranslator(model=model),
            title=title,
            confirm=confirm,
            progress=progress,
        )
    except GenerationCancelled as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=0) from exc
    except (OSError, PdfExtractionError, TranslationError, ValueError) as exc:
        typer.secho(f"Chyba: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(f"Vytvořeno: {result}", fg=typer.colors.GREEN)


def _duration(seconds: float) -> str:
    rounded = max(0, round(seconds))
    minutes, seconds_part = divmod(rounded, 60)
    return f"{minutes} min {seconds_part} s" if minutes else f"{seconds_part} s"


if __name__ == "__main__":
    app()
