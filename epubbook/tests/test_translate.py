from epubbook.models import TextSegment
from epubbook.translate import make_chunks


def test_chunks_keep_each_segment_once() -> None:
    segments = [TextSegment(index, "chapter.xhtml", "text " * 100) for index in range(30)]
    chunks = make_chunks(segments)
    assert [item.identifier for chunk in chunks for item in chunk] == list(range(30))
    assert len(chunks) > 1
