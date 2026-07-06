# Architecture

The project is split into small units so that each processing step can be replaced without
rewriting the whole pipeline.

## Pipeline

1. `fetch.fetch_html` downloads the source page.
2. `extract.extract_article` removes page noise and returns clean article HTML and text.
3. `translate.Translator` translates the article HTML. `NoopTranslator` is used for tests
   and dry runs; `OpenAITranslator` is the first production provider.
4. `epub.write_epub` writes the final EPUB.

## Design choices

- `src/` layout prevents accidental imports from the project root.
- Pydantic models validate article and book metadata at the pipeline boundaries.
- Provider interfaces keep external services out of the core logic.
- Tests avoid live network calls and paid translation calls.

## Next technical steps

- chunk long articles before translation to stay inside model limits
- cache fetched and extracted articles for repeatable runs
- add per-site extraction rules for sources where readability is not enough
- optionally add a browser-based fetcher for JavaScript-heavy pages

