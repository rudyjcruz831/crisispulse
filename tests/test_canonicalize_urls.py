from pipelines.canonicalize_urls import canonicalize_url, source_domain


def test_canonicalize_removes_tracking_fragment_and_default_port() -> None:
    raw = "HTTPS://Example.COM:443//news/story/?b=2&utm_source=email&a=1#details"
    canonical = canonicalize_url(raw)
    assert canonical == "https://example.com/news/story?a=1&b=2"
    assert source_domain(canonical) == "example.com"


def test_canonicalize_rejects_non_http_urls() -> None:
    assert canonicalize_url("javascript:alert(1)") is None
    assert canonicalize_url("") is None
