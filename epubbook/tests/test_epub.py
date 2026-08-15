from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from epubbook.epub import EPUB_MIMETYPE, load_epub, write_translated_epub


def create_epub(path: Path) -> None:
    container = b"""<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
 <rootfiles>
  <rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/>
 </rootfiles>
</container>"""
    package = b"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
 <item id="css" href="style.css" media-type="text/css"/></manifest>
 <spine><itemref idref="chapter"/></spine>
</package>"""
    chapter = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Internal title</title>
<link rel="stylesheet" href="style.css"/></head><body><h1 class="heading">Hello</h1>
<p> Read <em>this</em> book. </p><pre>do not translate</pre></body></html>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", EPUB_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OPS/content.opf", package)
        archive.writestr("OPS/chapter.xhtml", chapter)
        archive.writestr("OPS/style.css", b".heading { color: red; }")


def test_translation_preserves_archive_assets_and_markup(tmp_path: Path) -> None:
    source = tmp_path / "source.epub"
    output = tmp_path / "translated.epub"
    create_epub(source)
    book = load_epub(source)

    texts = [slot.segment.text.strip() for slot in book.slots]
    assert texts == ["Hello", "Read", "this", "book."]
    translations = {
        slot.segment.identifier: f"CZ:{slot.segment.text.strip()}" for slot in book.slots
    }
    write_translated_epub(book, translations, output)

    with zipfile.ZipFile(output) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.infolist()[0].compress_type == zipfile.ZIP_STORED
        assert archive.read("OPS/style.css") == b".heading { color: red; }"
        root = etree.fromstring(archive.read("OPS/chapter.xhtml"))
        assert root.xpath("string(//*[local-name()='h1'])") == "CZ:Hello"
        paragraph = root.xpath("//*[local-name()='p']")[0]
        assert paragraph.get("class") is None
        assert "CZ:Read" in "".join(paragraph.itertext())
        assert root.xpath("string(//*[local-name()='pre'])") == "do not translate"


def test_analysis_estimates_input_and_output_tokens(tmp_path: Path) -> None:
    source = tmp_path / "source.epub"
    create_epub(source)
    analysis = load_epub(source).analysis
    assert analysis.document_count == 1
    assert analysis.segment_count == 4
    assert analysis.character_count > 0
    assert analysis.estimated_tokens > analysis.character_count / 4
