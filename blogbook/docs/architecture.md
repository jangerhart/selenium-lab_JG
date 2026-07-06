# Architecture

The project is split into small units so that each processing step can be replaced without
rewriting the whole pipeline.

## Pipeline

1. `pipeline.read_urls` loads one or more source URLs from a text file.
2. `fetch.fetch_html` downloads each source page.
3. `extract.extract_article` removes page noise and returns clean article HTML and text.
4. `translate.Translator` translates the article HTML into Czech. `NoopTranslator` is used for tests
   and dry runs; `OpenAITranslator` is the first production provider.
5. `epub.write_epub` writes the final EPUB with one chapter per URL.

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
