"""Transparent first-pass grouping for likely syndicated article copies."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import unquote, urlsplit


GENERIC_SLUG_TOKENS = {"article", "index", "news", "story", "update", "latest"}


def _slug_tokens(segment: str) -> list[str]:
    slug = re.sub(
        r"\.(?:html?|aspx?|php)$", "", unquote(segment), flags=re.IGNORECASE
    )
    return [
        token
        for token in re.findall(r"[a-z0-9]+", slug.lower())
        if not token.isdigit() and token not in GENERIC_SLUG_TOKENS
    ]


def title_like_path_segment(canonical_url: str | None) -> str | None:
    """Return the last human-readable URL segment, skipping trailing IDs."""
    if not canonical_url:
        return None
    segments = [segment for segment in urlsplit(canonical_url).path.split("/") if segment]
    for segment in reversed(segments):
        decoded = re.sub(
            r"\.(?:html?|aspx?|php)$", "", unquote(segment), flags=re.IGNORECASE
        ).strip()
        if not decoded or decoded.isdigit():
            continue
        if re.fullmatch(
            r"(?:article[_-]?)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
            decoded,
            flags=re.IGNORECASE,
        ):
            continue
        words = re.findall(r"[^\W\d_]+", decoded, flags=re.UNICODE)
        if len(words) >= 3 or (len(words) >= 2 and sum(map(len, words)) >= 8):
            return decoded
    return None


def normalized_story_slug(canonical_url: str | None) -> str | None:
    """Extract a conservative title-like key, skipping trailing numeric IDs."""
    if not canonical_url:
        return None
    segments = [segment for segment in urlsplit(canonical_url).path.split("/") if segment]
    if not segments:
        return None
    for segment in reversed(segments):
        tokens = _slug_tokens(segment)
        if len(tokens) >= 5:
            return "-".join(tokens)
    return None


def story_group(
    canonical_url: str | None,
    seen_at: datetime | None,
    disaster_type: str,
    article_id: str,
) -> tuple[str, str]:
    """Return a six-hour slug group when reliable, otherwise the article ID."""
    slug = normalized_story_slug(canonical_url)
    if slug is None or seen_at is None:
        return article_id, "canonical_url"
    bucket = seen_at.replace(hour=(seen_at.hour // 6) * 6, minute=0, second=0, microsecond=0)
    raw_group = f"{disaster_type}|{bucket:%Y%m%d%H}|{slug}"
    return hashlib.sha256(raw_group.encode("utf-8")).hexdigest(), "url_slug_6h"
