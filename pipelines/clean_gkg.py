"""Create a flood-focused silver Parquet dataset from GDELT GKG files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from pipelines.canonicalize_urls import canonicalize_url, source_domain
from pipelines.deduplicate import story_group
from pipelines.gdelt_schema import GKG_COLUMNS
from pipelines.parse_locations import (
    distinct_location_count,
    parse_enhanced_locations,
    select_primary_location,
)


DISASTER_MARKERS = {
    "flood": ("FLOOD",),
    "wildfire": ("WILDFIRE", "FOREST_FIRE", "WILD_FIRE"),
}
MATCH_STRENGTH = {"weak": 1, "high": 2}

OUTPUT_SCHEMA = {
    "source_file": pl.String,
    "record_id": pl.String,
    "article_id": pl.String,
    "seen_at": pl.Datetime(time_unit="us"),
    "canonical_url": pl.String,
    "source_domain": pl.String,
    "location_name": pl.String,
    "country_code": pl.String,
    "adm1_code": pl.String,
    "adm2_code": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
    "distinct_location_count": pl.Int64,
    "location_selection_status": pl.String,
    "location_candidate_regions": pl.List(pl.String),
    "disaster_type": pl.String,
    "disaster_match_strength": pl.String,
    "matched_disaster_themes": pl.List(pl.String),
    "themes": pl.List(pl.String),
    "tone": pl.Float64,
    "geo_confidence": pl.String,
    "quality_flags": pl.List(pl.String),
    "duplicate_group_id": pl.String,
    "duplicate_group_method": pl.String,
    "duplicate_group_size": pl.Int64,
}


@dataclass
class PipelineStats:
    input_files: int = 0
    input_rows: int = 0
    theme_matched_rows: int = 0
    weak_rows_skipped: int = 0
    disaster_rows: int = 0
    duplicate_rows: int = 0
    location_review_rows: int = 0
    ambiguous_region_rows: int = 0
    output_rows: int = 0


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # GDELT processing timestamps are UTC. Store them without a timezone so
        # local Windows runs do not require an operating-system timezone database.
        return datetime.strptime(value.strip(), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def parse_tone(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.split(",", maxsplit=1)[0])
    except ValueError:
        return None


def theme_tokens(row: dict[str, str]) -> list[str]:
    raw = ";".join((row.get("V1THEMES", ""), row.get("V2ENHANCEDTHEMES", "")))
    tokens = []
    for value in raw.split(";"):
        token = value.split(",", maxsplit=1)[0].strip().upper()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def classify_disaster(themes: list[str], disaster_type: str) -> tuple[str | None, list[str]]:
    markers = DISASTER_MARKERS[disaster_type]
    matched = [theme for theme in themes if any(marker in theme for marker in markers)]
    if not matched:
        return None, []

    if disaster_type == "flood":
        strong_suffixes = ("_FLOOD", "_FLOODS", "_FLOODING", "_FLASH_FLOODS")
        high = any(
            theme == "FLOOD"
            or (theme.endswith(strong_suffixes) and not theme.startswith("WB_"))
            for theme in matched
        )
    else:
        high = any(
            theme.endswith(("_WILDFIRE", "_WILDFIRES", "_FOREST_FIRE", "_WILD_FIRE"))
            for theme in matched
        )
    return ("high" if high else "weak"), matched


def matches_disaster(
    themes: list[str], disaster_type: str, minimum_strength: str = "high"
) -> bool:
    strength, _ = classify_disaster(themes, disaster_type)
    return bool(strength and MATCH_STRENGTH[strength] >= MATCH_STRENGTH[minimum_strength])


@contextmanager
def _text_reader(path: Path) -> Iterator[io.TextIOBase]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".csv", ".tsv"))
            ]
            if not members:
                raise ValueError(f"ZIP contains no CSV or TSV file: {path}")
            with archive.open(members[0]) as binary:
                with io.TextIOWrapper(
                    binary, encoding="utf-8", errors="replace", newline=""
                ) as reader:
                    yield reader
        return
    with path.open("r", encoding="utf-8", errors="replace", newline="") as reader:
        yield reader


def iter_gkg_rows(path: Path) -> Iterator[dict[str, str]]:
    """Read official headerless GKG files and compact headered test/sample files."""
    csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
    with _text_reader(path) as stream:
        reader = csv.reader(stream, delimiter="\t")
        first = next(reader, None)
        if first is None:
            return
        if "GKGRECORDID" in first and "V2DOCUMENTIDENTIFIER" in first:
            header = first
        else:
            header = GKG_COLUMNS
            yield dict(zip(header, first, strict=False))
        for values in reader:
            if not values or not any(values):
                continue
            yield dict(zip(header, values, strict=False))


def clean_file(
    input_path: Path,
    output_path: Path,
    disaster_type: str = "flood",
    minimum_strength: str = "high",
) -> PipelineStats:
    return clean_files([input_path], output_path, disaster_type, minimum_strength)


def clean_files(
    input_paths: Sequence[Path],
    output_path: Path,
    disaster_type: str = "flood",
    minimum_strength: str = "high",
) -> PipelineStats:
    if disaster_type not in DISASTER_MARKERS:
        raise ValueError(f"unsupported disaster type: {disaster_type}")
    if minimum_strength not in MATCH_STRENGTH:
        raise ValueError(f"unsupported minimum strength: {minimum_strength}")
    if not input_paths:
        raise ValueError("at least one input file is required")
    for input_path in input_paths:
        if not input_path.exists():
            raise FileNotFoundError(input_path)

    stats = PipelineStats(input_files=len(input_paths))
    records: list[dict[str, object]] = []
    seen_articles: set[str] = set()

    for input_path in input_paths:
        for row in iter_gkg_rows(input_path):
            stats.input_rows += 1
            themes = theme_tokens(row)
            match_strength, matched_themes = classify_disaster(themes, disaster_type)
            if match_strength is None:
                continue
            stats.theme_matched_rows += 1
            if MATCH_STRENGTH[match_strength] < MATCH_STRENGTH[minimum_strength]:
                stats.weak_rows_skipped += 1
                continue
            stats.disaster_rows += 1

            raw_url = row.get("V2DOCUMENTIDENTIFIER", "").strip()
            canonical_url = canonicalize_url(raw_url)
            identity_source = canonical_url or raw_url
            article_id = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()
            if article_id in seen_articles:
                stats.duplicate_rows += 1
                continue
            seen_articles.add(article_id)

            locations = parse_enhanced_locations(row.get("V2ENHANCEDLOCATIONS"))
            location_selection = select_primary_location(locations)
            primary = location_selection.location
            location_count = distinct_location_count(locations)
            timestamp = parse_timestamp(row.get("V2.1DATE"))
            duplicate_group_id, duplicate_group_method = story_group(
                canonical_url, timestamp, disaster_type, article_id
            )
            quality_flags: list[str] = []
            if canonical_url is None:
                quality_flags.append("invalid_url")
            if timestamp is None:
                quality_flags.append("invalid_seen_at")
            if primary is None:
                quality_flags.append("missing_location")
            elif not primary.valid_coordinates:
                quality_flags.append("invalid_coordinates")
            if location_count > 1:
                quality_flags.append("multiple_locations")
            if location_selection.status == "ambiguous_region":
                quality_flags.append("ambiguous_region")
                stats.ambiguous_region_rows += 1
            if location_selection.status == "unresolved_region":
                quality_flags.append("unresolved_region")
            if location_selection.status in {
                "missing",
                "ambiguous_region",
                "unresolved_region",
            }:
                stats.location_review_rows += 1

            records.append(
                {
                    "source_file": input_path.name,
                    "record_id": row.get("GKGRECORDID") or article_id,
                    "article_id": article_id,
                    "seen_at": timestamp,
                    "canonical_url": canonical_url,
                    "source_domain": source_domain(canonical_url)
                    or row.get("V2SOURCECOMMONNAME")
                    or None,
                    "location_name": primary.name if primary else None,
                    "country_code": primary.country_code if primary else None,
                    "adm1_code": primary.adm1_code if primary else None,
                    "adm2_code": primary.adm2_code if primary else None,
                    "latitude": primary.latitude if primary else None,
                    "longitude": primary.longitude if primary else None,
                    "distinct_location_count": location_count,
                    "location_selection_status": location_selection.status,
                    "location_candidate_regions": list(
                        location_selection.candidate_regions
                    ),
                    "disaster_type": disaster_type,
                    "disaster_match_strength": match_strength,
                    "matched_disaster_themes": matched_themes,
                    "themes": themes,
                    "tone": parse_tone(row.get("V1.5TONE")),
                    "geo_confidence": (
                        "coordinates_valid"
                        if primary and primary.valid_coordinates
                        else "location_only"
                        if primary
                        else "missing"
                    ),
                    "quality_flags": quality_flags,
                    "duplicate_group_id": duplicate_group_id,
                    "duplicate_group_method": duplicate_group_method,
                    "duplicate_group_size": 1,
                }
            )

    frame = pl.from_dicts(records, schema=OUTPUT_SCHEMA, strict=False)
    if frame.height:
        frame = frame.with_columns(
            pl.len().over("duplicate_group_id").cast(pl.Int64).alias("duplicate_group_size")
        ).sort(["seen_at", "article_id"], nulls_last=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(output_path, compression="zstd")
    stats.output_rows = frame.height
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="GKG TSV/CSV or ZIP file")
    parser.add_argument("--output", type=Path, required=True, help="clean Parquet destination")
    parser.add_argument("--disaster", choices=sorted(DISASTER_MARKERS), default="flood")
    parser.add_argument(
        "--minimum-strength",
        choices=sorted(MATCH_STRENGTH),
        default="high",
        help="high excludes ambiguous theme-only matches such as metaphorical 'flooded'",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = clean_file(args.input, args.output, args.disaster, args.minimum_strength)
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
