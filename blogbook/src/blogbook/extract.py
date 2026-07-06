from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup
from readability import Document

from blogbook.models import Article


class ExtractionError(RuntimeError):
    """Raised when a readable article cannot be extracted."""


def extract_article(html: str, source_url: str) -> Article:
    document = Document(html)
    title = _clean_text(document.short_title()) or _find_title(html)
    article_html = document.summary(html_partial=True)

    soup = BeautifulSoup(article_html, "html.parser")
    _remove_noise(soup)
    cleaned_html = _normalize_article_html(soup)
    text = _clean_text(soup.get_text("\n"))

    if not title or not text:
        title, cleaned_html, text = _fallback_extract(html)

    if not title or not cleaned_html or not text:
        raise ExtractionError("Could not extract a usable article from the page.")

    original_soup = BeautifulSoup(html, "html.parser")
    return Article.model_validate(
        {
            "source_url": source_url,
            "title": title,
            "author": _find_author(original_soup),
            "language": _find_language(original_soup),
            "html": cleaned_html,
            "text": text,
        }
    )


def _fallback_extract(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    _remove_noise(soup)
    root = soup.find("article") or soup.find("main") or soup.body
    if root is None:
        return "", "", ""
    title = _find_title(html)
    cleaned_html = _normalize_article_html(BeautifulSoup(str(root), "html.parser"))
    text = _clean_text(root.get_text("\n"))
    return title, cleaned_html, text


def _remove_noise(soup: BeautifulSoup) -> None:
    selectors = [
        "script",
        "style",
        "noscript",
        "iframe",
        "form",
        "nav",
        "footer",
        "aside",
        "[role='navigation']",
        "[aria-label*='cookie' i]",
        "[class*='cookie' i]",
        "[id*='cookie' i]",
        "[class*='advert' i]",
        "[id*='advert' i]",
        "[class*='promo' i]",
        "[class*='subscribe' i]",
        "[id*='subscribe' i]",
    ]
    for element in soup.select(", ".join(selectors)):
        element.decompose()


def _normalize_article_html(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(True):
        allowed_attrs = {"href", "src", "alt", "title"}
        tag.attrs = {key: value for key, value in tag.attrs.items() if key in allowed_attrs}
    return str(soup).strip()


def _find_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["meta[property='og:title']", "meta[name='twitter:title']"]:
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return _clean_text(str(tag["content"]))
    if soup.title and soup.title.string:
        return _clean_text(soup.title.string)
    heading = soup.find("h1")
    return _clean_text(heading.get_text(" ")) if heading else ""


def _find_author(soup: BeautifulSoup) -> Optional[str]:
    for selector in [
        "meta[name='author']",
        "meta[property='article:author']",
        "[rel='author']",
        ".author",
        ".byline",
    ]:
        tag = soup.select_one(selector)
        if not tag:
            continue
        value = tag.get("content") if tag.name == "meta" else tag.get_text(" ")
        cleaned = _clean_text(str(value))
        if cleaned:
            return cleaned
    return None


def _find_language(soup: BeautifulSoup) -> Optional[str]:
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        return _clean_text(str(html_tag["lang"]))
    return None


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()
