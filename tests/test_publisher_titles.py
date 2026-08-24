import socket
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from pipelines import publisher_titles
from pipelines.publisher_titles import (
    add_publisher_titles,
    extract_publisher_title,
    normalize_publisher_title,
)


def test_title_extraction_prefers_open_graph_and_normalizes_whitespace():
    html = """
    <html><head>
      <title>Fallback page title</title>
      <meta property="og:title" content="  River flooding   closes roads  ">
    </head></html>
    """

    assert extract_publisher_title(html) == "River flooding closes roads"


def test_title_extraction_rejects_bot_challenges_and_numeric_values():
    assert extract_publisher_title("<title>Just a moment...</title>") is None
    assert normalize_publisher_title("73487469") is None


def test_title_extraction_uses_json_ld_or_heading_when_metadata_is_generic():
    json_ld_html = """
    <html><head>
      <meta property="og:title" content="www.example.com">
      <script type="application/ld+json">
        {"@type":"NewsArticle","headline":"Floodwaters close three county roads"}
      </script>
    </head><body><h1>Fallback heading</h1></body></html>
    """
    assert extract_publisher_title(
        json_ld_html, "https://www.example.com/news/opaque-id"
    ) == "Floodwaters close three county roads"
    assert extract_publisher_title(
        "<html><body><h1>River evacuation order remains active</h1></body></html>"
    ) == "River evacuation order remains active"


def test_title_normalization_rejects_domains_routes_and_article_ids():
    assert normalize_publisher_title(
        "timesofindia.indiatimes.com",
        "https://timesofindia.indiatimes.com/story/1",
    ) is None
    assert normalize_publisher_title("view negotiation") is None
    assert normalize_publisher_title(
        "article 54bf1eb7 5a48 4209 9cad 341913dfe371"
    ) is None
    assert normalize_publisher_title("Access Restricted in Your Area | Publisher") is None
    assert normalize_publisher_title("Title of the Page") is None
    assert normalize_publisher_title("8-19-26 - KAJN Radio") is None
    assert normalize_publisher_title(
        "KAJN Jesus FM 102.9",
        "https://kajn.com/8-19-26",
    ) is None


def test_title_cache_avoids_repeated_publisher_requests(tmp_path):
    cache_path = tmp_path / "publisher-title-cache.json"
    url = "https://news.example/flooding-closes-roads"
    stories = [{"sources": [{"url": url, "domain": "news.example"}]}]
    calls = []
    now = datetime(2026, 8, 21, tzinfo=UTC)

    def fetcher(requested_url: str) -> str:
        calls.append(requested_url)
        return "Flooding closes roads across the county"

    add_publisher_titles(stories, cache_path, fetcher=fetcher, now=now)

    cached_stories = [{"sources": [{"url": url, "domain": "news.example"}]}]
    add_publisher_titles(
        cached_stories,
        cache_path,
        fetcher=lambda _: (_ for _ in ()).throw(AssertionError("cache miss")),
        now=now + timedelta(hours=1),
    )

    assert calls == [url]
    assert stories[0]["title"] == "Flooding closes roads across the county"
    assert cached_stories[0]["title"] == stories[0]["title"]


def test_public_url_check_rejects_private_network_destinations(monkeypatch):
    monkeypatch.setattr(
        publisher_titles.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    assert not publisher_titles._is_public_http_url("https://news.example/story")

    monkeypatch.setattr(
        publisher_titles.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    assert publisher_titles._is_public_http_url("https://news.example/story")
    assert not publisher_titles._is_public_http_url("https://user:secret@news.example/story")
    assert not publisher_titles._is_public_http_url("https://news.example:8443/story")


def test_public_connection_pins_the_validated_numeric_address(monkeypatch):
    dns_calls = []
    sockets = []

    class FakeSocket:
        def __init__(self, family, socktype, protocol):
            self.created_with = (family, socktype, protocol)
            self.connected_to = None
            self.timeout = None
            sockets.append(self)

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect(self, address):
            self.connected_to = address

        def close(self):
            pass

    def resolve(hostname, port, **kwargs):
        dns_calls.append((hostname, port, kwargs))
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ]

    monkeypatch.setattr(publisher_titles.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(publisher_titles.socket, "socket", FakeSocket)

    connection = publisher_titles._create_public_connection(
        ("news.example", 443),
        timeout=2,
    )

    assert connection is sockets[0]
    assert len(dns_calls) == 1
    assert dns_calls[0][0:2] == ("news.example", 443)
    assert sockets[0].connected_to == ("93.184.216.34", 443)
    assert sockets[0].timeout == 2


def test_dns_rebinding_to_private_address_is_blocked_before_connect(monkeypatch):
    answers = iter(
        [
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
        ]
    )
    socket_creations = []

    monkeypatch.setattr(
        publisher_titles.socket,
        "getaddrinfo",
        lambda *args, **kwargs: next(answers),
    )
    monkeypatch.setattr(
        publisher_titles.socket,
        "socket",
        lambda *args, **kwargs: socket_creations.append((args, kwargs)),
    )

    assert publisher_titles.read_publisher_title("https://news.example/story") is None
    assert socket_creations == []


def test_pinned_https_connection_preserves_hostname_for_tls(monkeypatch):
    class RawSocket:
        def setsockopt(self, *args):
            pass

    class FakeTLSContext:
        def __init__(self):
            self.calls = []

        def wrap_socket(self, sock, *, server_hostname):
            self.calls.append((sock, server_hostname))
            return "tls-socket"

    raw_socket = RawSocket()
    tls_context = FakeTLSContext()
    connection = publisher_titles._PinnedHTTPSConnection(
        "news.example",
        context=tls_context,
    )
    monkeypatch.setattr(
        connection,
        "_create_connection",
        lambda address, timeout, source_address: raw_socket,
    )

    connection.connect()

    assert connection.sock == "tls-socket"
    assert tls_context.calls == [(raw_socket, "news.example")]


def test_pinned_http_connection_keeps_original_host_header():
    class RecordingSocket:
        def __init__(self):
            self.payloads = []

        def sendall(self, payload):
            self.payloads.append(payload)

    recording_socket = RecordingSocket()
    connection = publisher_titles._PinnedHTTPConnection("news.example")
    connection.sock = recording_socket

    connection.request("GET", "/story")

    request_bytes = b"".join(recording_socket.payloads)
    assert b"Host: news.example\r\n" in request_bytes


def test_redirect_handler_revalidates_each_target(monkeypatch):
    checked_urls = []

    def is_public(url):
        checked_urls.append(url)
        return False

    monkeypatch.setattr(publisher_titles, "_is_public_http_url", is_public)
    handler = publisher_titles._SafeRedirectHandler()
    request = Request("https://news.example/story")

    with pytest.raises(HTTPError, match="unsafe redirect blocked"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/admin",
        )

    assert checked_urls == ["http://127.0.0.1/admin"]
