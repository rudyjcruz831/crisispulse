"""Load small, auditable title corrections for pages that cannot be automated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pipelines.publisher_titles import normalize_publisher_title


OVERRIDE_VERSION = 1
MAX_OVERRIDE_FILE_BYTES = 1_000_000
DEFAULT_OVERRIDE_PATH = Path(__file__).with_name("publisher_title_overrides.json")


def _valid_public_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    expected_port = 443 if parsed.scheme == "https" else 80
    if port not in {None, expected_port}:
        return None
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return None
    return value


def load_publisher_title_overrides(
    path: Path = DEFAULT_OVERRIDE_PATH,
) -> dict[str, str]:
    """Return validated URL-to-title overrides from the checked-in audit file."""
    if path.stat().st_size > MAX_OVERRIDE_FILE_BYTES:
        raise ValueError("publisher title override file exceeds the size limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != OVERRIDE_VERSION:
        raise ValueError("unsupported publisher title override version")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("publisher title override entries must be a list")

    overrides: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"publisher title override {index} must be an object")
        url = _valid_public_url(entry.get("url"))
        title = normalize_publisher_title(entry.get("title"), url)
        if not url or not title:
            raise ValueError(f"publisher title override {index} is invalid")
        if url in overrides:
            raise ValueError(f"duplicate publisher title override URL: {url}")
        overrides[url] = title
    return overrides
