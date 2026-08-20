"""Conservative URL normalization for article identity."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "vero_conv",
    "vero_id",
}
TRACKING_PREFIXES = ("utm_",)


def canonicalize_url(raw_url: str | None) -> str | None:
    """Return a stable HTTP(S) URL, or ``None`` when the input is unusable."""
    if not raw_url or not raw_url.strip():
        return None

    try:
        parsed = urlsplit(raw_url.strip())
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            return None

        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            hostname = f"{hostname}:{port}"

        path = re.sub(r"/{2,}", "/", parsed.path or "/")
        if path != "/":
            path = path.rstrip("/")

        query_pairs = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.lower()
            if lowered in TRACKING_PARAMETERS or lowered.startswith(TRACKING_PREFIXES):
                continue
            query_pairs.append((key, value))
        query_pairs.sort(key=lambda item: (item[0].lower(), item[1]))
        query = urlencode(query_pairs, doseq=True)
        return urlunsplit((scheme, hostname, path, query, ""))
    except (UnicodeError, ValueError):
        return None


def source_domain(canonical_url: str | None) -> str | None:
    """Extract the lower-case hostname from a canonical URL."""
    if not canonical_url:
        return None
    return urlsplit(canonical_url).hostname
