# Pdfbook

Pdfbook translates machine-readable PDF books into Czech and creates a new, cleanly
typeset PDF focused on text. It is intended for PDFs containing selectable text, not scans.

The application:

- extracts text locally before making any OpenAI API request
- removes standalone source page numbers
- detects and removes headers and footers repeated across pages
- preserves the remaining text, including copyright notices in the book content
- shows the page count, text size, approximate input + output token use, and asks for
  confirmation before translation
- translates in bounded chunks and displays progress with an estimated remaining time
- creates a new A4 PDF without trying to reproduce the source layout

## Setup

Pdfbook reads the same `OPENAI_API_KEY` (or fallback `API_KEY`) environment variable as
Blogbook.

```bash
cd pdfbook
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Usage

```bash
export OPENAI_API_KEY="..."

pdfbook translate input/book.pdf \
  --output output/pdf/book-cs.pdf \
  --title "Český název knihy"
```

The default translation model is `gpt-4.1-mini`. Select another model with `--model`.
Use `--yes` only for unattended runs where the preflight confirmation should be skipped.

The original PDF is only read and is never modified.

## Development

```bash
ruff check .
mypy src
pytest
```
