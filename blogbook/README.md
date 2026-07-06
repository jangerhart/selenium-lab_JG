# Blogbook

Blogbook creates small EPUB e-books from web blog posts. The pipeline downloads a page,
extracts the main article, optionally translates it, and writes a clean EPUB file.

## Status

This is an MVP scaffold:

- article extraction from HTML with `readability-lxml` and a BeautifulSoup fallback
- translation provider abstraction with OpenAI implementation
- EPUB generation with `ebooklib`
- CLI entrypoint
- unit tests for the core pipeline

## Setup

```bash
cd blogbook
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Usage

Create an EPUB without translation:

```bash
blogbook create "https://example.com/blog-post" --output output/book.epub --no-translate
```

Create a Czech translation with OpenAI:

```bash
export OPENAI_API_KEY="..."
blogbook create "https://example.com/blog-post" --language cs --output output/book.epub
```

Use `--title` and `--author` when the source page metadata is incomplete.

## Development

```bash
ruff check .
mypy src
pytest
```

## Notes

Respect copyright and the source site's terms. This tool is intended for personal reading,
archiving allowed content, or processing content you have permission to reuse.
