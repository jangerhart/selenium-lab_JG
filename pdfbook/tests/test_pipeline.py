from pathlib import Path

import pytest

import pdfbook.pipeline as pipeline
from pdfbook.models import BookSection, ExtractionResult


def _result() -> ExtractionResult:
    return ExtractionResult(
        sections=[BookSection(text="Source paragraph.", source_page=1)],
        page_count=1,
        character_count=500,
        estimated_tokens=400,
        removed_header_footer_lines=[],
    )


def test_confirmation_happens_before_api_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    class Translator:
        def translate_sections(self, sections: object, progress: object = None) -> list[str]:
            nonlocal called
            called = True
            return ["Překlad."]

    monkeypatch.setattr(pipeline, "extract_pdf", lambda _: _result())

    with pytest.raises(pipeline.GenerationCancelled):
        pipeline.translate_pdf(
            tmp_path / "input.pdf",
            tmp_path / "output.pdf",
            Translator(),  # type: ignore[arg-type]
            confirm=lambda _: False,
        )

    assert called is False


def test_pipeline_writes_translated_paragraphs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    class Translator:
        def translate_sections(self, sections: object, progress: object = None) -> list[str]:
            return ["První.\n\n[[PARAGRAPH]]\n\nDruhý."]

    monkeypatch.setattr(pipeline, "extract_pdf", lambda _: _result())
    monkeypatch.setattr(
        pipeline,
        "write_pdf",
        lambda paragraphs, output, title: captured.extend(paragraphs) or output,
    )

    pipeline.translate_pdf(
        tmp_path / "input.pdf",
        tmp_path / "output.pdf",
        Translator(),  # type: ignore[arg-type]
        confirm=lambda _: True,
    )

    assert captured == ["První.", "Druhý."]
