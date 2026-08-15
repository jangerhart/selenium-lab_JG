from __future__ import annotations

import time
from pathlib import Path

import typer

from epubbook.epub import EpubError
from epubbook.models import EpubAnalysis
from epubbook.pipeline import GenerationCancelled, translate_epub
from epubbook.translate import OpenAITranslator, TranslationError

app = typer.Typer(no_args_is_help=True, help="Přeloží EPUB do češtiny bez změny sazby knihy.")


@app.command()
def translate(
    input_epub: Path = typer.Argument(..., help="Zdrojová kniha EPUB."),
    output: Path = typer.Option(Path("output/translated-cs.epub"), "--output", "-o"),
    model: str = typer.Option("gpt-4.1-mini", "--model"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Přeskočit potvrzení analýzy."),
) -> None:
    started = time.monotonic()

    def confirm(result: EpubAnalysis) -> bool:
        typer.echo("\nAnalýza vstupního EPUB")
        typer.echo(f"  XHTML dokumentů:         {result.document_count}")
        typer.echo(f"  Textových částí:         {result.segment_count}")
        typer.echo(f"  Znaků k překladu:        {result.character_count:,}".replace(",", " "))
        typer.echo(f"  Odhad tokenů:            ~{result.estimated_tokens:,}".replace(",", " "))
        typer.echo("  Odhad zahrnuje vstup, výstup a režii; skutečná spotřeba se může lišit.\n")
        return yes or typer.confirm("Pokračovat v překladu?", default=False)

    def progress(current: int, total: int, detail: str) -> None:
        elapsed = time.monotonic() - started
        eta = (elapsed / current) * max(total - current, 0)
        typer.echo(f"[Překlad {current}/{total}] {detail} | odhad zbývá {_duration(eta)}")

    try:
        result = translate_epub(input_epub, output, OpenAITranslator(model), confirm, progress)
    except GenerationCancelled as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=0) from exc
    except (EpubError, TranslationError, OSError, ValueError) as exc:
        typer.secho(f"Chyba: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Vytvořeno: {result}", fg=typer.colors.GREEN)


def _duration(seconds: float) -> str:
    rounded = max(0, round(seconds))
    minutes, remainder = divmod(rounded, 60)
    return f"{minutes} min {remainder} s" if minutes else f"{remainder} s"


if __name__ == "__main__":
    app()
