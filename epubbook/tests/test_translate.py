import pytest

from epubbook.models import TextSegment
from epubbook.translate import (
    OpenAITranslator,
    ResponseValidationError,
    TranslationError,
    _strip_json_fence,
    make_chunks,
)


def test_chunks_keep_each_segment_once() -> None:
    segments = [TextSegment(index, "chapter.xhtml", "text " * 100) for index in range(30)]
    chunks = make_chunks(segments)
    assert [item.identifier for chunk in chunks for item in chunk] == list(range(30))
    assert len(chunks) > 1


def test_invalid_block_is_automatically_split(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[int]] = []

    def fake_translate(
        self: OpenAITranslator, segments: list[TextSegment]
    ) -> dict[int, str]:
        identifiers = [segment.identifier for segment in segments]
        calls.append(identifiers)
        if len(segments) > 1:
            raise ResponseValidationError("missing id")
        return {segments[0].identifier: f"CZ {segments[0].text}"}

    monkeypatch.setattr(OpenAITranslator, "_translate_chunk", fake_translate)
    segments = [TextSegment(index, "chapter.xhtml", f"text {index}") for index in range(4)]
    result = OpenAITranslator().translate(segments)

    assert set(result) == {0, 1, 2, 3}
    assert calls[0] == [0, 1, 2, 3]
    assert [0] in calls and [3] in calls


def test_single_invalid_segment_is_retried_three_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def always_invalid(
        self: OpenAITranslator, segments: list[TextSegment]
    ) -> dict[int, str]:
        nonlocal attempts
        attempts += 1
        raise ResponseValidationError("invalid")

    monkeypatch.setattr(OpenAITranslator, "_translate_chunk", always_invalid)
    with pytest.raises(TranslationError, match="po 3 pokusech"):
        OpenAITranslator().translate([TextSegment(7, "chapter.xhtml", "text")])
    assert attempts == 3


def test_markdown_json_fence_is_accepted() -> None:
    assert _strip_json_fence("```json\n[{\"id\": 1, \"text\": \"Ahoj\"}]\n```").startswith("[")
