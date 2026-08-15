# Epubbook

Epubbook překládá existující knihy EPUB do češtiny, aniž by je znovu sázel. Mění pouze
viditelné textové uzly v XHTML dokumentech. Původní HTML struktura, CSS, obrázky, fonty,
odkazy, poznámky, obsah, pořadí kapitol a ostatní soubory archivu zůstávají zachované.

Před prvním API požadavkem nástroj lokálně načte knihu a zobrazí počet XHTML dokumentů,
textových částí, znaků a přibližnou spotřebu vstupních i výstupních tokenů. Překlad lze
v tomto bodě bezpečně zrušit. Zdrojový soubor se nikdy nemění.

## Instalace

```bash
cd epubbook
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Použití

```bash
export OPENAI_API_KEY="..."
epubbook translate input/book.epub --output output/book-cs.epub
```

Výchozí model je `gpt-4.1-mini`; změnit jej lze přes `--model`. Přepínač `--yes` přeskočí
potvrzení po analýze. EPUB musí používat validní XML/XHTML; tím lze strukturu měnit
bez heuristického opravování a rizika poškození sazby.
