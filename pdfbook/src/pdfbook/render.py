from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Optional

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def write_pdf(paragraphs: list[str], output_path: Path, title: Optional[str] = None) -> Path:
    if not paragraphs:
        raise ValueError("Nelze vytvořit PDF bez textu.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = _register_unicode_font()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BookBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        alignment=TA_JUSTIFY,
        spaceAfter=5 * mm,
        splitLongWords=True,
    )
    title_style = ParagraphStyle(
        "BookTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=12 * mm,
    )
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
        title=title or output_path.stem,
        author="",
    )
    story = []
    if title:
        story.extend([Spacer(1, 45 * mm), Paragraph(escape(title), title_style), PageBreak()])
    for paragraph in paragraphs:
        safe_text = escape(paragraph).replace("\n", "<br/>")
        story.append(Paragraph(safe_text, body))
    document.build(story)
    return output_path


def _register_unicode_font() -> str:
    for path in FONT_CANDIDATES:
        if path.exists():
            name = "PdfbookUnicode"
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
    return "Helvetica"
