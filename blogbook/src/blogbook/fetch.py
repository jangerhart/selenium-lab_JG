from __future__ import annotations

import httpx

DEFAULT_USER_AGENT = (
    "Blogbook/0.1 (+https://example.invalid/blogbook; personal reading epub generator)"
)


class FetchError(RuntimeError):
    """Raised when a web page cannot be fetched."""


def fetch_html(url: str, timeout_seconds: float = 20.0) -> str:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not fetch {url}: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and response.text.strip().startswith("<") is False:
        raise FetchError(f"URL did not return HTML: {url}")

    return response.text
