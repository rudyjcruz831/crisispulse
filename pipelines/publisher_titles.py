"""Fetch a small, safe, cached set of publisher page titles."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser


USER_AGENT = "CrisisPulseTitleFetcher/0.1 (local research; cached requests)"
MAX_HTML_BYTES = 256 * 1024
MAX_ROBOTS_BYTES = 64 * 1024
MAX_TITLE_LENGTH = 240
MAX_TITLE_FETCHES = 12
MAX_CACHE_ENTRIES = 2048
FETCH_TIMEOUT_SECONDS = 4
SUCCESS_TTL = timedelta(days=30)
MISS_TTL = timedelta(hours=6)


class _PublisherTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self._title_parts: list[str] = []
        self._metadata: dict[str, str] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "title":
            self._inside_title = True
            return
        if lowered_tag != "meta":
            return
        values = {
            str(key).lower(): str(value)
            for key, value in attrs
            if key and value is not None
        }
        key = (values.get("property") or values.get("name") or "").lower()
        if key in {"og:title", "twitter:title"} and values.get("content"):
            self._metadata.setdefault(key, values["content"])

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self._title_parts.append(data)

    def best_title(self) -> str | None:
        candidates = [
            self._metadata.get("og:title"),
            self._metadata.get("twitter:title"),
            " ".join(self._title_parts),
        ]
        for candidate in candidates:
            title = normalize_publisher_title(candidate)
            if title:
                return title
        return None


def normalize_publisher_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    title = " ".join(unescape(value).replace("\u200b", " ").split()).strip()
    if len(title) < 5 or not any(character.isalpha() for character in title):
        return None
    blocked_titles = {
        "access denied",
        "attention required! | cloudflare",
        "error",
        "home",
        "just a moment...",
        "page not found",
        "request unsuccessful",
    }
    if title.casefold() in blocked_titles:
        return None
    return title[:MAX_TITLE_LENGTH].rstrip()


def extract_publisher_title(html: str) -> str | None:
    parser = _PublisherTitleParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return None
    return parser.best_title()


def _is_public_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    expected_port = 443 if parsed.scheme == "https" else 80
    if port not in {None, expected_port}:
        return False
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return False
    try:
        addresses = socket.getaddrinfo(
            hostname, expected_port, type=socket.SOCK_STREAM
        )
    except OSError:
        return False
    if not addresses:
        return False
    try:
        return all(
            ipaddress.ip_address(address[4][0].split("%", 1)[0]).is_global
            for address in addresses
        )
    except ValueError:
        return False


class _SafeRedirectHandler(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        target = urljoin(req.full_url, newurl)
        if not _is_public_http_url(target):
            raise HTTPError(target, 403, "unsafe redirect blocked", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _request(url: str, *, accept: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": accept,
            "Connection": "close",
            "Range": f"bytes=0-{MAX_HTML_BYTES - 1}",
            "User-Agent": USER_AGENT,
        },
    )


def _robots_allows(url: str, opener) -> bool:  # noqa: ANN001
    parsed = urlparse(url)
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    try:
        with opener.open(
            _request(robots_url, accept="text/plain,*/*;q=0.1"),
            timeout=FETCH_TIMEOUT_SECONDS,
        ) as response:
            payload = response.read(MAX_ROBOTS_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except HTTPError as error:
        return error.code not in {401, 403, 429} and error.code < 500
    except (OSError, URLError, TimeoutError):
        return False

    parser = RobotFileParser(robots_url)
    parser.parse(payload.decode(charset, errors="replace").splitlines())
    return parser.can_fetch(USER_AGENT, url)


def read_publisher_title(url: str) -> str | None:
    """Return an Open Graph, Twitter, or HTML title without raising."""
    if not _is_public_http_url(url):
        return None
    opener = build_opener(_SafeRedirectHandler())
    if not _robots_allows(url, opener):
        return None
    try:
        with opener.open(
            _request(url, accept="text/html,application/xhtml+xml;q=0.9"),
            timeout=FETCH_TIMEOUT_SECONDS,
        ) as response:
            final_url = response.geturl()
            if not _is_public_http_url(final_url):
                return None
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return None
            payload = response.read(MAX_HTML_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except (HTTPError, OSError, URLError, TimeoutError, ValueError):
        return None
    return extract_publisher_title(payload.decode(charset, errors="replace"))


def _read_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        entries = payload.get("entries")
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}
    if not isinstance(entries, dict):
        return {}
    return {
        str(url): entry
        for url, entry in entries.items()
        if isinstance(url, str) and isinstance(entry, dict)
    }


def _cache_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_cache(cache_path: Path, entries: dict[str, dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    retained = dict(
        sorted(
            entries.items(),
            key=lambda item: str(item[1].get("fetched_at") or ""),
            reverse=True,
        )[:MAX_CACHE_ENTRIES]
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=cache_path.parent,
            prefix=f"{cache_path.name}.",
            suffix=".partial",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump({"version": 1, "entries": retained}, temporary, indent=2)
            temporary.write("\n")
        os.replace(temporary_path, cache_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def fetch_publisher_titles(
    urls: list[str],
    cache_path: Path,
    *,
    fetcher: Callable[[str], str | None] = read_publisher_title,
    now: datetime | None = None,
) -> dict[str, str]:
    """Resolve cached titles and fetch a bounded number of cache misses."""
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    unique_urls = list(dict.fromkeys(url for url in urls if isinstance(url, str)))
    entries = _read_cache(cache_path)
    titles: dict[str, str] = {}
    misses: list[str] = []

    for url in unique_urls:
        entry = entries.get(url, {})
        fetched_at = _cache_time(entry.get("fetched_at"))
        status = str(entry.get("status") or "")
        title = normalize_publisher_title(entry.get("title"))
        ttl = SUCCESS_TTL if status == "ok" and title else MISS_TTL
        if fetched_at is not None and current_time - fetched_at <= ttl:
            if title:
                titles[url] = title
            continue
        misses.append(url)

    pending = misses[:MAX_TITLE_FETCHES]
    if pending:
        with ThreadPoolExecutor(max_workers=min(3, len(pending))) as executor:
            futures = {executor.submit(fetcher, url): url for url in pending}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    title = normalize_publisher_title(future.result())
                except Exception:
                    title = None
                entries[url] = {
                    "status": "ok" if title else "miss",
                    "title": title,
                    "fetched_at": current_time.isoformat(),
                }
                if title:
                    titles[url] = title

    if pending:
        try:
            _write_cache(cache_path, entries)
        except OSError:
            pass
    return titles


def add_publisher_titles(
    stories: list[dict[str, Any]],
    cache_path: Path,
    *,
    fetcher: Callable[[str], str | None] = read_publisher_title,
    now: datetime | None = None,
) -> None:
    """Add one verified publisher title per story, preserving URL fallbacks."""
    primary_urls = [
        str(story["sources"][0].get("url") or "")
        for story in stories
        if isinstance(story.get("sources"), list) and story["sources"]
    ]
    titles = fetch_publisher_titles(
        primary_urls, cache_path, fetcher=fetcher, now=now
    )
    for story in stories:
        sources = story.get("sources")
        if not isinstance(sources, list) or not sources:
            continue
        url = str(sources[0].get("url") or "")
        story["title"] = titles.get(url)
