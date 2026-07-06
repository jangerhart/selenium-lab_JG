from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from blogbook.pipeline import create_book_from_url
from blogbook.translate import NoopTranslator, OpenAITranslator

app = typer.Typer(
    no_args_is_help=True,
    help="Create small translated EPUB e-books from blog posts.",
)


@app.command()
def create(
    url: str = typer.Argument(..., help="Blog post URL."),
    output: Path = typer.Option(Path("book.epub"), "--output", "-o", help="Output EPUB path."),
    language: str = typer.Option("cs", "--language", "-l", help="Target language code."),
    title: Optional[str] = typer.Option(None, "--title", help="Override book title."),
    author: Optional[str] = typer.Option(None, "--author", help="Override book author."),
    translate: bool = typer.Option(
        True,
        "--translate/--no-translate",
        help="Translate article text.",
    ),
    model: str = typer.Option("gpt-4.1-mini", "--model", help="OpenAI model for translation."),
) -> None:
    translator = OpenAITranslator(model=model) if translate else NoopTranslator()
    result = create_book_from_url(
        url=url,
        output_path=output,
        translator=translator,
        target_language=language,
        title=title,
        author=author,
    )
    typer.echo(f"Created EPUB: {result}")


if __name__ == "__main__":
    app()
