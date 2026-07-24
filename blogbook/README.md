# Blogbook

Blogbook creates small Czech EPUB e-books from web blog posts. The pipeline reads URLs
from a text file, downloads each page, extracts the main article, optionally translates it
into Czech, and writes a clean EPUB file.

## Status

This is an MVP scaffold:

- article extraction from HTML with `readability-lxml` and a BeautifulSoup fallback
- translation provider abstraction with OpenAI implementation
- EPUB generation with `ebooklib`, including one chapter per input URL
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

Create `urls.txt` with one blog post URL per line:

```text
https://example.com/blog-post
https://example.com/another-post
```

Create a Czech EPUB with OpenAI translation:

```bash
export OPENAI_API_KEY="..."
blogbook create urls.txt --output output/book.epub
```

Before translation, Blogbook checks every URL, extracts its readable content, skips
unreachable or non-article pages, and displays a summary with an approximate translation
token count. Translation starts only after confirmation. During both checking and translation
the CLI displays progress and an estimated remaining time. Use `--yes` for unattended runs.

Create an EPUB without translation, useful for local extraction checks:

```bash
blogbook create urls.txt --output output/book.epub --no-translate
```

Use `--title` when you want to override the generated book title. Chapter titles are derived
from each article header. The author is inferred from page metadata when available; otherwise
it is omitted from the EPUB metadata.

## Development

```bash
ruff check .
mypy src
pytest
```

## Notes

Respect copyright and the source site's terms. This tool is intended for personal reading,
archiving allowed content, or processing content you have permission to reuse.
