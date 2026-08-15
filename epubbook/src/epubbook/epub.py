from __future__ import annotations

import math
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lxml import etree

from epubbook.models import EpubAnalysis, TextSegment

CONTAINER = "META-INF/container.xml"
EPUB_MIMETYPE = b"application/epub+zip"
XHTML_MEDIA_TYPE = "application/xhtml+xml"
SKIPPED_ELEMENTS = {"script", "style", "title", "code", "pre"}


class EpubError(RuntimeError):
    """Raised when an EPUB cannot be safely read or updated."""


@dataclass
class TextSlot:
    segment: TextSegment
    element: etree._Element
    attribute: str


@dataclass
class LoadedEpub:
    input_path: Path
    entries: dict[str, bytes]
    infos: list[zipfile.ZipInfo]
    roots: dict[str, etree._Element]
    slots: list[TextSlot]
    analysis: EpubAnalysis


def load_epub(input_path: Path) -> LoadedEpub:
    try:
        with zipfile.ZipFile(input_path) as archive:
            infos = archive.infolist()
            entries = {info.filename: archive.read(info) for info in infos if not info.is_dir()}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise EpubError(f"EPUB nelze otevřít: {exc}") from exc

    if entries.get("mimetype", b"").strip() != EPUB_MIMETYPE:
        raise EpubError("Soubor nemá platný EPUB mimetype.")
    opf_name = _package_path(entries)
    document_names = _xhtml_paths(entries, opf_name)

    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    roots: dict[str, etree._Element] = {}
    slots: list[TextSlot] = []
    next_id = 0
    for name in document_names:
        try:
            root = etree.fromstring(entries[name], parser=parser)
        except etree.XMLSyntaxError as exc:
            raise EpubError(f"Neplatné XHTML v {name}: {exc}") from exc
        roots[name] = root
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            local_name = etree.QName(element).localname.lower()
            if local_name in SKIPPED_ELEMENTS or _has_skipped_ancestor(element):
                continue
            for attribute in ("text", "tail"):
                value = getattr(element, attribute)
                if value and _is_translatable(value):
                    segment = TextSegment(next_id, name, value)
                    slots.append(TextSlot(segment, element, attribute))
                    next_id += 1

    characters = sum(len(slot.segment.text) for slot in slots)
    if not slots:
        raise EpubError("EPUB neobsahuje žádný přeložitelný text.")
    analysis = EpubAnalysis(
        document_count=len(roots),
        segment_count=len(slots),
        character_count=characters,
        estimated_tokens=estimate_translation_tokens(characters, len(slots)),
    )
    return LoadedEpub(input_path, entries, infos, roots, slots, analysis)


def write_translated_epub(
    book: LoadedEpub, translations: dict[int, str], output_path: Path
) -> Path:
    expected = {slot.segment.identifier for slot in book.slots}
    if set(translations) != expected:
        raise EpubError("Překlad neobsahuje přesně všechny textové části knihy.")
    for slot in book.slots:
        translated = _restore_whitespace(
            slot.segment.text, translations[slot.segment.identifier]
        )
        setattr(slot.element, slot.attribute, translated)

    updated = dict(book.entries)
    for name, root in book.roots.items():
        original = book.entries[name]
        declaration = original.lstrip().startswith(b"<?xml")
        updated[name] = etree.tostring(root, encoding="utf-8", xml_declaration=declaration)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output_path, "w") as archive:
            archive.writestr("mimetype", EPUB_MIMETYPE, compress_type=zipfile.ZIP_STORED)
            written = {"mimetype"}
            for info in book.infos:
                if info.is_dir() or info.filename in written:
                    continue
                archive.writestr(info, updated[info.filename])
                written.add(info.filename)
    except OSError as exc:
        raise EpubError(f"Výstupní EPUB nelze zapsat: {exc}") from exc
    return output_path


def estimate_translation_tokens(characters: int, segment_count: int) -> int:
    # Input and expected Czech output, plus JSON/protocol overhead per text node.
    input_tokens = math.ceil(characters / 4) + segment_count * 6 + 200
    return input_tokens + math.ceil(input_tokens * 1.15)


def _package_path(entries: dict[str, bytes]) -> str:
    try:
        root = etree.fromstring(entries[CONTAINER])
        paths = root.xpath("//*[local-name()='rootfile']/@full-path")
    except (KeyError, etree.XMLSyntaxError) as exc:
        raise EpubError("EPUB nemá platný META-INF/container.xml.") from exc
    if not paths or paths[0] not in entries:
        raise EpubError("EPUB odkazuje na chybějící OPF balíček.")
    return str(paths[0])


def _xhtml_paths(entries: dict[str, bytes], opf_name: str) -> list[str]:
    try:
        root = etree.fromstring(entries[opf_name])
    except etree.XMLSyntaxError as exc:
        raise EpubError(f"Neplatný OPF balíček: {exc}") from exc
    base = posixpath.dirname(opf_name)
    paths = []
    for item in root.xpath("//*[local-name()='manifest']/*[local-name()='item']"):
        if item.get("media-type") != XHTML_MEDIA_TYPE or not item.get("href"):
            continue
        name = posixpath.normpath(posixpath.join(base, item.get("href")))
        if name.startswith("../") or PurePosixPath(name).is_absolute() or name not in entries:
            raise EpubError(f"Neplatná nebo chybějící XHTML položka: {name}")
        paths.append(name)
    if not paths:
        raise EpubError("OPF manifest neobsahuje žádné XHTML dokumenty.")
    return paths


def _has_skipped_ancestor(element: etree._Element) -> bool:
    return any(
        isinstance(parent.tag, str)
        and etree.QName(parent).localname.lower() in SKIPPED_ELEMENTS
        for parent in element.iterancestors()
    )


def _is_translatable(value: str) -> bool:
    return bool(value.strip()) and any(character.isalpha() for character in value)


def _restore_whitespace(source: str, translated: str) -> str:
    leading = source[: len(source) - len(source.lstrip())]
    trailing = source[len(source.rstrip()) :]
    return leading + translated.strip() + trailing
