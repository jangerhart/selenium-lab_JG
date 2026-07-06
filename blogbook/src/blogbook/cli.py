from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from blogbook.pipeline import create_book_from_file
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
) -> None:
    translator = OpenAITranslator(model=model) if translate else NoopTranslator()
    try:
        result = create_book_from_file(
            urls_file=urls_file,
            output_path=output,
            translator=translator,
            title=title,
        )
    except (OSError, RuntimeError, TranslationError, ValueError) as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created EPUB: {result}")


if __name__ == "__main__":
    app()
