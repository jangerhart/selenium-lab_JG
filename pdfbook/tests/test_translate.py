from pdfbook.models import BookSection
from pdfbook.translate import make_chunks, translated_paragraphs


def test_chunks_preserve_paragraph_markers() -> None:
    sections = [
        BookSection(text="First paragraph.", source_page=1),
        BookSection(text="Second paragraph.", source_page=1),
    ]

    chunks = make_chunks(sections)

    assert len(chunks) == 1
    assert "[[PARAGRAPH]]" in chunks[0]
    assert translated_paragraphs(chunks) == ["First paragraph.", "Second paragraph."]
