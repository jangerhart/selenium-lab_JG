from pathlib import Path

import pytest

import epubbook.pipeline as pipeline
from epubbook.epub import LoadedEpub
from epubbook.models import EpubAnalysis, TextSegment


def test_decline_happens_before_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False
    analysis = EpubAnalysis(1, 1, 5, 100)
    fake_book = LoadedEpub(tmp_path / "in.epub", {}, [], {}, [], analysis)

    class Translator:
        def translate(self, segments: list[TextSegment], progress: object = None) -> dict[int, str]:
            nonlocal called
            called = True
            return {}

    monkeypatch.setattr(pipeline, "load_epub", lambda _: fake_book)
    with pytest.raises(pipeline.GenerationCancelled):
        pipeline.translate_epub(
            tmp_path / "in.epub",
            tmp_path / "out.epub",
            Translator(),
            confirm=lambda _: False,
        )
    assert called is False
