"""Fail-closed semantic validation for CrisisPulse backup data."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import polars as pl


FEATURE_REQUIRED_COLUMNS = {
    "window_start",
    "region_id",
    "article_count",
    "estimated_unique_story_count",
}
ARTICLE_REQUIRED_COLUMNS = {
    "article_id",
    "seen_at",
    "canonical_url",
    "source_domain",
    "disaster_type",
}
REVIEW_LOGS = ("reviews.jsonl", "article-reviews.jsonl")
MAX_REVIEW_LOG_BYTES = 4 << 20
MAX_REVIEW_LINE_BYTES = 16 << 10
MAX_DASHBOARD_BYTES = 2 << 20
MAX_REFRESH_STATUS_BYTES = 256 << 10
FUTURE_TOLERANCE = timedelta(minutes=1)
REGION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,63}$")
ARTICLE_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)
WINDOW_START_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})?$"
)
SIGNAL_DECISIONS = {"confirmed_event", "irrelevant_news", "uncertain"}
LEGACY_ARTICLE_DECISIONS = {"relevant", "not_relevant", "uncertain"}
ARTICLE_DECISIONS_V2 = {
    "reported_flooding",
    "flood_risk_warning",
    "heavy_rain_only",
    "not_flood_related",
    "uncertain",
}
ARTICLE_DECISION_SCHEMA_VERSION = 2
ARTICLE_TAG_MAX_COUNT = 8
ARTICLE_TAG_MAX_LENGTH = 32
MATCH_STRENGTHS = {"high", "weak"}
REVIEW_BUCKETS = {"high_match", "headline_conflict", "ambiguous_match"}


class ValidationError(ValueError):
    """Application data is unsafe to publish as a verified backup."""


def _reject_nonstandard_constant(value: str) -> None:
    raise ValidationError(f"non-standard JSON constant is not allowed: {value}")


def _parse_json(text: str, *, label: str) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_nonstandard_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValidationError(f"{label} is not valid JSON") from error


def _read_json_object(
    path: Path,
    *,
    label: str,
    max_bytes: int,
) -> dict[str, Any]:
    try:
        if path.stat().st_size > max_bytes:
            raise ValidationError(f"{label} exceeds its size limit")
        payload = _parse_json(path.read_text(encoding="utf-8"), label=label)
    except (OSError, UnicodeDecodeError) as error:
        raise ValidationError(f"{label} cannot be read") from error
    if not isinstance(payload, dict):
        raise ValidationError(f"{label} must contain a JSON object")
    return payload


def _validate_dashboard(path: Path) -> None:
    payload = _read_json_object(
        path,
        label="dashboard.json",
        max_bytes=MAX_DASHBOARD_BYTES,
    )
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValidationError("dashboard.json is missing the snapshot object")
    if not isinstance(snapshot.get("updated_label"), str) or not snapshot[
        "updated_label"
    ].strip():
        raise ValidationError("dashboard.json is missing snapshot.updated_label")
    if not isinstance(payload.get("signals"), list):
        raise ValidationError("dashboard.json is missing the signals array")


def _rfc3339(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_PATTERN.fullmatch(value):
        raise ValidationError(f"refresh-status.json is missing {field}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValidationError(f"refresh-status.json has an invalid {field}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"refresh-status.json {field} must include a timezone")
    return parsed


def _validate_refresh_status(path: Path) -> None:
    payload = _read_json_object(
        path,
        label="refresh-status.json",
        max_bytes=MAX_REFRESH_STATUS_BYTES,
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != 3:
        raise ValidationError("refresh-status.json must use schema version 3")
    if payload.get("status") != "success":
        raise ValidationError("refresh-status.json must record a successful refresh")
    started_at = _rfc3339(payload.get("started_at"), field="started_at")
    finished_at = _rfc3339(payload.get("finished_at"), field="finished_at")
    last_success_at = _rfc3339(
        payload.get("last_success_at"), field="last_success_at"
    )
    if finished_at < started_at:
        raise ValidationError("refresh-status.json finishes before it starts")
    if last_success_at != finished_at:
        raise ValidationError(
            "refresh-status.json last_success_at must match finished_at"
        )
    future_limit = datetime.now(UTC) + FUTURE_TOLERANCE
    if any(value > future_limit for value in (started_at, finished_at, last_success_at)):
        raise ValidationError("refresh-status.json contains a future timestamp")


def _string_field(payload: dict[str, Any], field: str, *, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ValidationError(f"{label} has an invalid {field}")
    return value


def _parse_record_timestamp(value: str, *, label: str) -> None:
    if not RFC3339_PATTERN.fullmatch(value):
        raise ValidationError(f"{label} has an invalid timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValidationError(f"{label} has an invalid timestamp") from error


def _byte_length(value: str) -> int:
    return len(value.encode("utf-8"))


def _safe_external_url(value: str) -> bool:
    if not 1 <= _byte_length(value) <= 2048:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if port is not None and not (
        (parsed.scheme == "http" and port == 80)
        or (parsed.scheme == "https" and port == 443)
    ):
        return False
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
    )


def _validate_signal_review(payload: dict[str, Any], *, label: str) -> None:
    signal_id = _string_field(payload, "signal_id", label=label)
    region_code = _string_field(payload, "region_code", label=label)
    window_start = _string_field(payload, "window_start", label=label)
    decision = _string_field(payload, "decision", label=label)
    reviewed_at = _string_field(payload, "reviewed_at", label=label)
    if not REGION_CODE_PATTERN.fullmatch(region_code):
        raise ValidationError(f"{label} has an invalid region_code")
    if not 19 <= len(window_start) <= 40 or not WINDOW_START_PATTERN.fullmatch(
        window_start
    ):
        raise ValidationError(f"{label} has an invalid window_start")
    try:
        datetime.fromisoformat(window_start.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"{label} has an invalid window_start") from error
    if decision not in SIGNAL_DECISIONS:
        raise ValidationError(f"{label} has an invalid decision")
    if signal_id != f"{region_code}|{window_start}":
        raise ValidationError(f"{label} has an inconsistent signal_id")
    _parse_record_timestamp(reviewed_at, label=label)


def _validate_article_review(payload: dict[str, Any], *, label: str) -> None:
    article_id = _string_field(payload, "article_id", label=label)
    title = _string_field(payload, "title", label=label)
    url = _string_field(payload, "url", label=label)
    source_domain = _string_field(payload, "source_domain", label=label)
    match_strength = _string_field(payload, "match_strength", label=label)
    review_bucket = _string_field(payload, "review_bucket", label=label)
    decision = _string_field(payload, "decision", label=label)
    reviewed_at = _string_field(payload, "reviewed_at", label=label)
    decision_schema_version = payload.get("decision_schema_version", 1)
    tags = payload.get("tags", [])
    if not ARTICLE_ID_PATTERN.fullmatch(article_id):
        raise ValidationError(f"{label} has an invalid article_id")
    if not 1 <= _byte_length(title) <= 1024 or _byte_length(source_domain) > 255:
        raise ValidationError(f"{label} has invalid article evidence")
    if not _safe_external_url(url):
        raise ValidationError(f"{label} has an invalid url")
    if match_strength not in MATCH_STRENGTHS:
        raise ValidationError(f"{label} has an invalid match_strength")
    if review_bucket not in REVIEW_BUCKETS:
        raise ValidationError(f"{label} has an invalid review_bucket")
    if (
        isinstance(decision_schema_version, bool)
        or not isinstance(decision_schema_version, int)
        or decision_schema_version not in {1, ARTICLE_DECISION_SCHEMA_VERSION}
    ):
        raise ValidationError(f"{label} has an invalid decision_schema_version")
    allowed_decisions = (
        LEGACY_ARTICLE_DECISIONS
        if decision_schema_version == 1
        else ARTICLE_DECISIONS_V2
    )
    if decision not in allowed_decisions:
        raise ValidationError(f"{label} has an invalid decision")
    if not isinstance(tags, list) or len(tags) > ARTICLE_TAG_MAX_COUNT:
        raise ValidationError(f"{label} has invalid article tags")
    if decision_schema_version == 1 and tags:
        raise ValidationError(f"{label} version 1 cannot contain article tags")
    seen_tags: set[str] = set()
    for tag in tags:
        if (
            not isinstance(tag, str)
            or not tag
            or len(tag) > ARTICLE_TAG_MAX_LENGTH
            or tag != tag.lower()
            or tag.startswith("-")
            or tag.endswith("-")
            or "--" in tag
            or any(
                character != "-"
                and not (
                    unicodedata.category(character).startswith("L")
                    or unicodedata.category(character) == "Nd"
                )
                for character in tag
            )
            or tag in seen_tags
        ):
            raise ValidationError(f"{label} has invalid article tags")
        seen_tags.add(tag)
    _parse_record_timestamp(reviewed_at, label=label)


def _validate_review_log(path: Path) -> None:
    if not path.exists():
        return
    try:
        if path.stat().st_size > MAX_REVIEW_LOG_BYTES:
            raise ValidationError(f"{path.name} exceeds the review log size limit")
        with path.open("rb") as source:
            for line_number, raw_line in enumerate(source, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                if len(stripped) > MAX_REVIEW_LINE_BYTES:
                    raise ValidationError(
                        f"{path.name} line {line_number} exceeds the line size limit"
                    )
                try:
                    line = stripped.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValidationError(
                        f"{path.name} line {line_number} is not valid UTF-8"
                    ) from error
                label = f"{path.name} line {line_number}"
                payload = _parse_json(
                    line,
                    label=label,
                )
                if not isinstance(payload, dict):
                    raise ValidationError(
                        f"{path.name} line {line_number} must be a JSON object"
                    )
                if path.name == "reviews.jsonl":
                    _validate_signal_review(payload, label=label)
                else:
                    _validate_article_review(payload, label=label)
    except OSError as error:
        raise ValidationError(f"{path.name} cannot be read") from error


def _read_parquet(
    path: Path,
    *,
    label: str,
    required_columns: set[str],
) -> pl.DataFrame:
    try:
        frame = pl.read_parquet(path, memory_map=False)
    except (OSError, pl.exceptions.PolarsError) as error:
        raise ValidationError(f"{label} is not a readable Parquet file") from error
    if frame.is_empty():
        raise ValidationError(f"{label} must not be empty")
    missing = required_columns.difference(frame.columns)
    if missing:
        raise ValidationError(f"{label} is missing required columns: {sorted(missing)}")
    return frame


def _validate_parquets(work_root: Path) -> None:
    history = work_root / "history"
    _read_parquet(
        history / "hourly_region_features.parquet",
        label="hourly_region_features.parquet",
        required_columns=FEATURE_REQUIRED_COLUMNS,
    )
    articles = _read_parquet(
        history / "flood_articles_archive.parquet",
        label="flood_articles_archive.parquet",
        required_columns=ARTICLE_REQUIRED_COLUMNS,
    )
    if articles.schema["article_id"] != pl.String:
        raise ValidationError("flood_articles_archive.parquet article_id must be text")
    article_ids = articles.get_column("article_id")
    if article_ids.null_count():
        raise ValidationError("flood_articles_archive.parquet contains a null article_id")
    if article_ids.str.strip_chars().eq("").any():
        raise ValidationError("flood_articles_archive.parquet contains an empty article_id")
    if article_ids.n_unique() != articles.height:
        raise ValidationError(
            "flood_articles_archive.parquet contains duplicate article_id values"
        )


def validate_application_data(state_root: Path, work_root: Path) -> None:
    _validate_dashboard(state_root / "dashboard.json")
    _validate_refresh_status(state_root / "refresh-status.json")
    for review_log in REVIEW_LOGS:
        _validate_review_log(state_root / review_log)
    _validate_parquets(work_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_application_data(args.state_root, args.work_root)
    except (ValidationError, OSError) as error:
        print(f"Application data validation failed: {error}", file=sys.stderr)
        return 1
    print("Application data verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
