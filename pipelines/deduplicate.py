"""Transparent first-pass grouping for likely syndicated article copies."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import unquote, unquote_plus, urlsplit


GENERIC_SLUG_TOKENS = {"article", "index", "news", "story", "update", "latest"}
GENERIC_PATH_PHRASES = {
    "article",
    "articleshow",
    "home",
    "index",
    "latest",
    "news",
    "story",
    "stories",
    "view",
    "view negotiation",
}
GENERIC_ROUTE_TOKENS = {
    "category",
    "channel",
    "headlines",
    "local",
    "national",
    "news",
    "regional",
    "section",
    "topic",
    "world",
}
HEADLINE_ACRONYMS = {
    "cm": "CM",
    "fema": "FEMA",
    "npr": "NPR",
    "nws": "NWS",
    "uk": "UK",
    "un": "UN",
    "us": "US",
    "usa": "USA",
    "wnc": "WNC",
}
LOWERCASE_HEADLINE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "nor",
    "of",
    "on",
    "or",
    "over",
    "per",
    "the",
    "to",
    "up",
    "via",
    "with",
}
FILE_EXTENSION_PATTERN = re.compile(
    r"\.(?:s?html?|aspx?|php|cfm|cms)$",
    flags=re.IGNORECASE,
)
UUID_PATTERN = re.compile(
    r"(?:article[_-]?)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
    flags=re.IGNORECASE,
)
OPAQUE_HEX_PATTERN = re.compile(r"[0-9a-f]{16,}", flags=re.IGNORECASE)
DATE_PREFIX_PATTERN = re.compile(
    r"^(?:19|20)\d{2}[-_.](?:0?[1-9]|1[0-2])[-_.](?:0?[1-9]|[12]\d|3[01])[-_.]+"
)
TIMESTAMP_SUFFIX_PATTERN = re.compile(r"(?:19|20)\d{12}$")
LEADING_ID_PATTERN = re.compile(r"^\d{5,}[._-]+")
TRAILING_ID_PATTERN = re.compile(
    r"(?:[._-]+)(?:\d{5,}|[0-9a-f]{16,})$",
    flags=re.IGNORECASE,
)


def _slug_tokens(segment: str) -> list[str]:
    slug = FILE_EXTENSION_PATTERN.sub("", unquote(segment))
    return [
        token
        for token in re.findall(r"[a-z0-9]+", slug.lower())
        if not token.isdigit() and token not in GENERIC_SLUG_TOKENS
    ]


def _clean_title_segment(segment: str) -> str:
    """Strip common routing IDs while retaining the human-readable slug."""
    decoded = FILE_EXTENSION_PATTERN.sub("", unquote_plus(segment)).strip()
    if UUID_PATTERN.fullmatch(decoded):
        return ""
    decoded = DATE_PREFIX_PATTERN.sub("", decoded)
    decoded = LEADING_ID_PATTERN.sub("", decoded)
    decoded = TIMESTAMP_SUFFIX_PATTERN.sub("", decoded)
    decoded = TRAILING_ID_PATTERN.sub("", decoded)
    decoded = re.sub(r"^[._-]+|[._-]+$", "", decoded)
    return decoded.strip()


def _is_title_like_segment(segment: str) -> bool:
    if (
        not segment
        or segment.isdigit()
        or UUID_PATTERN.fullmatch(segment)
        or OPAQUE_HEX_PATTERN.fullmatch(segment)
    ):
        return False
    normalized_phrase = " ".join(re.sub(r"[-_]+", " ", segment).split()).casefold()
    if normalized_phrase in GENERIC_PATH_PHRASES:
        return False
    words = re.findall(r"[^\W\d_]+", segment, flags=re.UNICODE)
    if len(words) <= 3 and any(word.casefold() in GENERIC_ROUTE_TOKENS for word in words):
        return False
    return len(words) >= 3 or (len(words) >= 2 and sum(map(len, words)) >= 8)


def title_like_path_segment(canonical_url: str | None) -> str | None:
    """Return the last human-readable URL segment after removing routing IDs."""
    if not canonical_url:
        return None
    segments = [segment for segment in urlsplit(canonical_url).path.split("/") if segment]
    for segment in reversed(segments):
        decoded = _clean_title_segment(segment)
        if _is_title_like_segment(decoded):
            return decoded
    return None


def display_headline_from_url(canonical_url: str | None) -> str | None:
    """Render a conservative display headline from a readable URL slug."""
    segment = title_like_path_segment(canonical_url)
    if segment is None:
        return None
    headline = re.sub(r"[-_]+", " ", segment)
    headline = re.sub(r"\s+", " ", headline).strip(" .,:;|/\\")
    words = re.findall(r"[^\W\d_]+", headline, flags=re.UNICODE)
    if not _is_title_like_segment(headline) or len(words) < 3:
        return None
    if headline.isascii() and headline.islower():
        rendered_words: list[str] = []
        parts = headline.split()
        for index, word in enumerate(parts):
            lowered = word.casefold()
            if lowered in HEADLINE_ACRONYMS:
                rendered_words.append(HEADLINE_ACRONYMS[lowered])
            elif 0 < index < len(parts) - 1 and lowered in LOWERCASE_HEADLINE_WORDS:
                rendered_words.append(lowered)
            else:
                rendered_words.append(word[:1].upper() + word[1:])
        headline = " ".join(rendered_words)
    return headline[:240].rstrip()


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
