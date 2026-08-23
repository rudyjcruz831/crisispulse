import socket
from datetime import UTC, datetime, timedelta

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
