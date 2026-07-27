from pdfbook.extract import (
    clean_page_text,
    estimate_translation_tokens,
    find_repeated_edge_lines,
    split_paragraphs,
)


def test_repeated_headers_footers_and_page_numbers_are_removed() -> None:
    pages = [
        "Example Book\nChapter One\nBody text on the first page.\n1",
        "Example Book\nChapter One\nBody text on the second page.\n2",
        "Example Book\nChapter Two\nBody text on the third page.\n3",
    ]

    repeated = find_repeated_edge_lines(pages)
    cleaned = clean_page_text(pages[0], repeated)

    assert "Example Book" in repeated
    assert "Example Book" not in cleaned
    assert "\n1" not in cleaned
    assert "Body text" in cleaned


def test_paragraphs_join_wrapped_lines_and_hyphenation() -> None:
    text = "This is a wrapped\nparagraph with trans-\nlation.\n\nSecond paragraph."

    assert split_paragraphs(text) == [
        "This is a wrapped paragraph with translation.",
        "Second paragraph.",
    ]


def test_token_estimate_includes_input_and_output() -> None:
    assert estimate_translation_tokens("x" * 4000) > 2000
