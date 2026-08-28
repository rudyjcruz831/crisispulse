"""Fetch a small, safe, cached set of publisher page titles."""

from __future__ import annotations

import ipaddress
from http.client import HTTPConnection, HTTPSConnection
import json
import os
import re
import socket
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)
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
TITLE_PARSER_VERSION = 5
MAX_JSON_LD_BYTES = 128 * 1024
MAX_JSON_LD_NODES = 256
GENERIC_PUBLISHER_TITLES = {
    "article",
    "home",
    "homepage",
    "latest news",
    "news",
    "please wait",
    "story",
    "untitled",
    "view",
    "view negotiation",
}


class _PublisherTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self._title_parts: list[str] = []
        self._inside_h1 = False
        self._current_h1_parts: list[str] = []
        self._current_h1_scoped = False
        self._headings: list[str] = []
        self._scoped_headings: list[str] = []
        self._head_depth = 0
        self._body_started = False
        self._main_depth = 0
        self._article_depth = 0
        self._inside_json_ld = False
        self._current_json_ld_parts: list[str] = []
        self._json_ld_blocks: list[str] = []
        self._metadata: dict[str, list[str]] = {
            "og:title": [],
            "twitter:title": [],
            "title": [],
            "headline": [],
        }

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "head":
            self._head_depth += 1
        elif lowered_tag == "body":
            self._body_started = True
        elif lowered_tag == "main":
            self._main_depth += 1
        elif lowered_tag == "article":
            self._article_depth += 1
        if lowered_tag == "title":
            self._inside_title = True
            return
        if lowered_tag == "h1":
            self._inside_h1 = True
            self._current_h1_parts = []
            self._current_h1_scoped = (
                self._main_depth > 0 or self._article_depth > 0
            )
            return
        if lowered_tag == "script":
            values = {
                str(key).lower(): str(value)
                for key, value in attrs
                if key and value is not None
            }
            if values.get("type", "").split(";", 1)[0].strip().lower() == "application/ld+json":
                self._inside_json_ld = True
                self._current_json_ld_parts = []
            return
        if lowered_tag != "meta":
            return
        values = {
            str(key).lower(): str(value)
            for key, value in attrs
            if key and value is not None
        }
        key = (
            values.get("property")
            or values.get("name")
            or values.get("itemprop")
            or ""
        ).lower()
        if (
            key in self._metadata
            and values.get("content")
            and (self._head_depth > 0 or not self._body_started)
        ):
            self._metadata[key].append(values["content"])

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "title":
            self._inside_title = False
        elif lowered_tag == "h1" and self._inside_h1:
            self._inside_h1 = False
            heading = " ".join(self._current_h1_parts)
            self._headings.append(heading)
            if self._current_h1_scoped:
                self._scoped_headings.append(heading)
            self._current_h1_parts = []
            self._current_h1_scoped = False
        elif lowered_tag == "script" and self._inside_json_ld:
            self._inside_json_ld = False
            block = "".join(self._current_json_ld_parts)
            if len(block.encode("utf-8", errors="ignore")) <= MAX_JSON_LD_BYTES:
                self._json_ld_blocks.append(block)
            self._current_json_ld_parts = []
        if lowered_tag == "head" and self._head_depth > 0:
            self._head_depth -= 1
        elif lowered_tag == "article" and self._article_depth > 0:
            self._article_depth -= 1
        elif lowered_tag == "main" and self._main_depth > 0:
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self._title_parts.append(data)
        if self._inside_h1:
            self._current_h1_parts.append(data)
        if self._inside_json_ld:
            self._current_json_ld_parts.append(data)

    def best_title(self, source_url: str | None = None) -> str | None:
        matched_json_ld, fallback_json_ld = _json_ld_headline_groups(
            self._json_ld_blocks,
            source_url,
        )
        candidates = [
            *self._metadata["og:title"],
            *self._metadata["twitter:title"],
            *matched_json_ld,
            *self._scoped_headings,
            *fallback_json_ld,
            *self._metadata["headline"],
            *self._metadata["title"],
            *self._headings,
            " ".join(self._title_parts),
        ]
        for candidate in candidates:
            title = normalize_publisher_title(candidate, source_url)
            if title:
                return title
        return None


def _normalized_document_url(
    value: Any,
    source_url: str | None = None,
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        absolute = urljoin(source_url or "", value.strip())
        parsed = urlparse(absolute)
        hostname = (parsed.hostname or "").casefold().removeprefix("www.")
        if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
            return None
        port = parsed.port
    except ValueError:
        return None
    default_port = (parsed.scheme.casefold() == "http" and port == 80) or (
        parsed.scheme.casefold() == "https" and port == 443
    )
    authority = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query_pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
    ]
    query = urlencode(sorted(query_pairs))
    return f"{authority}{path}{f'?{query}' if query else ''}"


def _json_ld_node_urls(value: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("url", "@id"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            candidates.append(candidate)
    main_entity = value.get("mainEntityOfPage")
    if isinstance(main_entity, str):
        candidates.append(main_entity)
    elif isinstance(main_entity, dict):
        for key in ("url", "@id"):
            candidate = main_entity.get(key)
            if isinstance(candidate, str):
                candidates.append(candidate)
    return candidates


def _json_ld_headline_groups(
    blocks: list[str],
    source_url: str | None = None,
) -> tuple[list[str], list[str]]:
    matched_candidates: list[tuple[int, str]] = []
    fallback_candidates: list[tuple[int, str]] = []
    visited = 0
    order = 0
    normalized_source_url = _normalized_document_url(source_url)

    def visit(value: Any, depth: int = 0) -> None:
        nonlocal order, visited
        if depth > 8 or visited >= MAX_JSON_LD_NODES:
            return
        visited += 1
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
            return
        if not isinstance(value, dict):
            return
        type_value = value.get("@type")
        types = type_value if isinstance(type_value, list) else [type_value]
        is_article = any(
            isinstance(item, str)
            and ("article" in item.casefold() or item.casefold() in {"newsstory", "reportage"})
            for item in types
        )
        if is_article:
            normalized_node_urls = {
                normalized
                for candidate in _json_ld_node_urls(value)
                if (normalized := _normalized_document_url(candidate, source_url))
            }
            url_matches = bool(
                normalized_source_url
                and normalized_source_url in normalized_node_urls
            )
            url_mismatches = bool(
                normalized_source_url
                and normalized_node_urls
                and not url_matches
            )
            if not url_mismatches and (url_matches or depth == 0):
                target = matched_candidates if url_matches else fallback_candidates
                for key in ("headline", "name"):
                    candidate = value.get(key)
                    if isinstance(candidate, str):
                        target.append((order, candidate))
                        order += 1
        elif depth == 0:
            # Some publishers omit @type on a simple top-level article object.
            # Never accept nested untyped headlines because those commonly
            # describe recommendations, navigation cards, or live-blog items.
            headline = value.get("headline")
            if isinstance(headline, str):
                fallback_candidates.append((order, headline))
                order += 1
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                visit(nested, depth + 1)

    for block in blocks:
        try:
            payload = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        visit(payload)
    return (
        [candidate for _order, candidate in sorted(matched_candidates)],
        [candidate for _order, candidate in sorted(fallback_candidates)],
    )


def _looks_like_domain_title(title: str, source_url: str | None) -> bool:
    compact = title.casefold().strip(" /.")
    if re.fullmatch(r"(?:www\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", compact):
        return True
    if not source_url:
        return False
    try:
        hostname = (urlparse(source_url).hostname or "").rstrip(".").casefold()
    except ValueError:
        return False
    host_variants = {hostname, hostname.removeprefix("www.")}
    normalized_title = re.sub(r"[^a-z0-9]+", "", compact)
    return any(
        normalized_title == re.sub(r"[^a-z0-9]+", "", host)
        for host in host_variants
        if host
    )


def _looks_like_publisher_brand(title: str, source_url: str | None) -> bool:
    if not source_url:
        return False
    try:
        hostname = (urlparse(source_url).hostname or "").removeprefix("www.")
    except ValueError:
        return False
    brand = re.sub(r"[^a-z0-9]+", "", hostname.split(".", 1)[0].casefold())
    words = re.findall(r"[a-z0-9]+", title.casefold())
    if not brand or not words or len(words) > 8:
        return False
    first_word = re.sub(r"[^a-z0-9]+", "", words[0])
    brand_markers = {"am", "fm", "homepage", "online", "radio", "station", "tv"}
    return first_word == brand and any(word in brand_markers for word in words[1:])


def normalize_publisher_title(
    value: Any,
    source_url: str | None = None,
) -> str | None:
    if not isinstance(value, str):
        return None
    decoded = unicodedata.normalize("NFKC", unescape(value))
    decoded = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in decoded
    )
    title = " ".join(decoded.split()).strip()
    if len(title) < 5 or not any(character.isalpha() for character in title):
        return None
    blocked_titles = {
        "access denied",
        "attention required! | cloudflare",
        "error",
        "home",
        "javascript disabled",
        "javascript is disabled",
        "just a moment...",
        "page not found",
        "request unsuccessful",
        "title of the page",
    }
    folded = title.casefold().strip()
    if folded in blocked_titles or folded in GENERIC_PUBLISHER_TITLES:
        return None
    if _looks_like_domain_title(title, source_url):
        return None
    if _looks_like_publisher_brand(title, source_url):
        return None
    if re.fullmatch(
        r"article\s+[0-9a-f]{8}(?:[\s-][0-9a-f]{4}){3}[\s-][0-9a-f]{12}",
        folded,
    ):
        return None
    if re.fullmatch(r"(?:error\s*)?(?:401|403|404|429|500|502|503)(?:\s+.*)?", folded):
        return None
    if re.fullmatch(
        r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}(?:\s*[-|]\s*.+)?",
        folded,
    ):
        return None
    if folded.startswith(
        (
            "access restricted",
            "content unavailable",
            "enable javascript",
            "javascript disabled",
            "javascript is disabled",
            "page unavailable",
            "please enable javascript",
            "please wait",
            "this site requires javascript",
            "temporarily unavailable",
            "you need to enable javascript",
        )
    ):
        return None
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    shortened = title[:MAX_TITLE_LENGTH].rsplit(" ", 1)[0].rstrip()
    return shortened or title[:MAX_TITLE_LENGTH].rstrip()


def extract_publisher_title(html: str, source_url: str | None = None) -> str | None:
    parser = _PublisherTitleParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return None
    return parser.best_title(source_url)


def _resolve_public_addresses(
    hostname: str,
    port: int,
) -> list[tuple[int, int, int, tuple[Any, ...]]]:
    """Resolve a host once and return only validated public socket addresses."""
    try:
        addresses = socket.getaddrinfo(
            hostname.rstrip(".").casefold(),
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        raise OSError("publisher hostname could not be resolved") from error
    if not addresses:
        raise OSError("publisher hostname did not resolve")

    resolved: list[tuple[int, int, int, tuple[Any, ...]]] = []
    seen: set[tuple[int, tuple[Any, ...]]] = set()
    for family, socktype, protocol, _canonical_name, socket_address in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            raise OSError("publisher hostname resolved to an unsupported address")
        try:
            address = ipaddress.ip_address(socket_address[0].split("%", 1)[0])
        except (ValueError, TypeError, IndexError) as error:
            raise OSError("publisher hostname resolved to an invalid address") from error
        if not address.is_global:
            raise OSError("publisher hostname resolved to a non-public address")
        key = (family, socket_address)
        if key in seen:
            continue
        seen.add(key)
        resolved.append((family, socktype, protocol, socket_address))

    if not resolved:
        raise OSError("publisher hostname did not resolve to a usable address")
    return resolved


def _create_public_connection(
    address: tuple[str, int],
    timeout: float | object = socket._GLOBAL_DEFAULT_TIMEOUT,
    source_address: tuple[str, int] | None = None,
):  # noqa: ANN202, SLF001
    """Connect to the exact public IPs returned by the validated DNS lookup."""
    hostname, port = address
    endpoints = _resolve_public_addresses(hostname, port)
    last_error: OSError | None = None
    for family, socktype, protocol, socket_address in endpoints:
        connection = socket.socket(family, socktype, protocol)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:  # noqa: SLF001
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            # socket_address is the numeric sockaddr produced and validated above,
            # so connect cannot perform a second hostname lookup.
            connection.connect(socket_address)
            return connection
        except OSError as error:
            last_error = error
            connection.close()
    if last_error is not None:
        raise last_error
    raise OSError("publisher hostname did not resolve to a usable address")


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self._create_connection = _create_public_connection


class _PinnedHTTPSConnection(HTTPSConnection):
    # HTTPSConnection still keeps the original hostname in ``self.host`` and
    # passes it to SSLContext.wrap_socket as server_hostname. Only the TCP
    # endpoint is pinned, preserving certificate validation and SNI.
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self._create_connection = _create_public_connection


class _PinnedHTTPHandler(HTTPHandler):
    def http_open(self, request):  # noqa: ANN001, ANN201
        return self.do_open(_PinnedHTTPConnection, request)


class _PinnedHTTPSHandler(HTTPSHandler):
    def https_open(self, request):  # noqa: ANN001, ANN201
        return self.do_open(
            _PinnedHTTPSConnection,
            request,
            context=self._context,
        )


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
        _resolve_public_addresses(hostname, expected_port)
    except OSError:
        return False
    return True


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
    opener = build_opener(
        ProxyHandler({}),
        _PinnedHTTPHandler(),
        _PinnedHTTPSHandler(),
        _SafeRedirectHandler(),
    )
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
    return extract_publisher_title(
        payload.decode(charset, errors="replace"),
        final_url,
    )


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
            json.dump(
                {"version": TITLE_PARSER_VERSION, "entries": retained},
                temporary,
                indent=2,
            )
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
    max_fetches: int = MAX_TITLE_FETCHES,
    max_workers: int = 3,
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
        parser_version = entry.get("parser_version")
        status = str(entry.get("status") or "")
        title = normalize_publisher_title(entry.get("title"), url)
        ttl = SUCCESS_TTL if status == "ok" and title else MISS_TTL
        if (
            parser_version == TITLE_PARSER_VERSION
            and fetched_at is not None
            and current_time - fetched_at <= ttl
        ):
            if title:
                titles[url] = title
            continue
        misses.append(url)

    pending = misses[: max(0, max_fetches)]
    if pending:
        with ThreadPoolExecutor(max_workers=min(max(1, max_workers), len(pending))) as executor:
            futures = {executor.submit(fetcher, url): url for url in pending}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    title = normalize_publisher_title(future.result(), url)
                except Exception:
                    title = None
                entries[url] = {
                    "status": "ok" if title else "miss",
                    "title": title,
                    "fetched_at": current_time.isoformat(),
                    "parser_version": TITLE_PARSER_VERSION,
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
