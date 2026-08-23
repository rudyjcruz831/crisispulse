"""Log stale refreshes and optionally send a throttled webhook alert."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


STATUS_URL = "http://api:8080/api/v1/admin/status"
WEBHOOK_URL = os.environ.get("CRISISPULSE_ALERT_WEBHOOK_URL", "").strip()
INTERVAL_SECONDS = max(
    30, int(os.environ.get("CRISISPULSE_MONITOR_INTERVAL_SECONDS", "60"))
)
ALERT_THROTTLE_SECONDS = 30 * 60


def _status() -> dict[str, object]:
    request = Request(STATUS_URL, headers={"User-Agent": "CrisisPulse-Monitor/1.0"})
    # The service URL is a fixed, internal address.
    with urlopen(request, timeout=10) as response:  # nosec B310
        return json.load(response)


def _validated_webhook_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if not hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("alert webhook URL is invalid")
    if parsed.fragment:
        raise ValueError("alert webhook URL must not contain a fragment")
    if parsed.scheme == "https":
        return value
    if parsed.scheme == "http" and hostname in {"127.0.0.1", "localhost", "::1"}:
        return value
    raise ValueError("alert webhook URL must use HTTPS")


def _send_alert(message: str) -> None:
    if not WEBHOOK_URL:
        return
    webhook_url = _validated_webhook_url(WEBHOOK_URL)
    body = json.dumps(
        {
            "text": message,
            "service": "CrisisPulse",
            "observed_at": datetime.now(UTC).isoformat(),
        }
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    # The webhook URL is restricted to HTTPS immediately before this call.
    with urlopen(request, timeout=10):  # nosec B310
        pass


def main() -> None:
    last_alert_at = 0.0
    while True:
        message = ""
        try:
            payload = _status()
            refresh = payload.get("refresh")
            health = refresh.get("health") if isinstance(refresh, dict) else None
            if health != "healthy":
                age = refresh.get("age_minutes") if isinstance(refresh, dict) else None
                message = f"CrisisPulse refresh is {health or 'unknown'} (age: {age} minutes)."
        except (OSError, ValueError, URLError, json.JSONDecodeError) as error:
            message = f"CrisisPulse health check failed: {error}"

        if message:
            print(message, flush=True)
            now = time.monotonic()
            if now - last_alert_at >= ALERT_THROTTLE_SECONDS:
                try:
                    _send_alert(message)
                except (OSError, ValueError, URLError) as error:
                    print(f"CrisisPulse alert delivery failed: {error}", flush=True)
                last_alert_at = now
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
