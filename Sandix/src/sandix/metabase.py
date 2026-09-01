from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class MetabaseConfig:
    base_url: str
    api_key: str
    collection_id: int | None = None
    dashboard_id: int | None = None


def get_metabase_config() -> MetabaseConfig:
    base_url = os.getenv("METABASE_URL")
    api_key = os.getenv("METABASE_API_KEY")
    if not base_url:
        raise RuntimeError("Missing required environment variable: METABASE_URL")
    if not api_key:
        raise RuntimeError("Missing required environment variable: METABASE_API_KEY")
    collection_id = os.getenv("METABASE_COLLECTION_ID")
    dashboard_id = os.getenv("METABASE_DASHBOARD_ID")
    return MetabaseConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        collection_id=int(collection_id) if collection_id else None,
        dashboard_id=int(dashboard_id) if dashboard_id else None,
    )


def metabase_request(method: str, path: str, body: dict[str, object] | None = None) -> object:
    config = get_metabase_config()
    data = None if body is None else json.dumps(body).encode()
    request = Request(
        f"{config.base_url}{path}",
        data=data,
        headers={"x-api-key": config.api_key, "Content-Type": "application/json"},
        method=method,
    )
    with urlopen(request, timeout=60) as response:
        payload = response.read().decode()
        return json.loads(payload) if payload else None


def metabase_get(path: str) -> object:
    return metabase_request("GET", path)


def metabase_post(path: str, body: dict[str, object] | None = None) -> object:
    return metabase_request("POST", path, body)


def metabase_put(path: str, body: dict[str, object] | None = None) -> object:
    return metabase_request("PUT", path, body)


def metabase_delete(path: str) -> object:
    return metabase_request("DELETE", path)


def metabase_error_message(exc: HTTPError) -> str:
    try:
        return exc.read().decode()
    except Exception:
        return str(exc)
