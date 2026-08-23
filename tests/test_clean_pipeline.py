from pathlib import Path
import zipfile

import polars as pl

from pipelines.clean_gkg import clean_file
from pipelines.gdelt_schema import GKG_COLUMNS
from pipelines.hourly_counts import hourly_counts
from pipelines.inspect_clean import build_report


SAMPLE = Path(__file__).parents[1] / "data" / "sample" / "gkg_sample.tsv"


def test_flood_pipeline_filters_canonicalizes_and_deduplicates(tmp_path: Path) -> None:
    output = tmp_path / "floods.parquet"
    stats = clean_file(SAMPLE, output, "flood")
    frame = pl.read_parquet(output)

    assert stats.input_rows == 5
    assert stats.theme_matched_rows == 4
    assert stats.weak_rows_skipped == 0
    assert stats.disaster_rows == 4
    assert stats.duplicate_rows == 1
    assert stats.output_rows == 3
    assert frame["canonical_url"].to_list() == [
        "https://example.com/news/veracruz-flood",
        "https://bayou.test/weather/high-water?section=local",
        "https://regional.test/river/flood-warning",
    ]
    assert "invalid_coordinates" in frame.row(2, named=True)["quality_flags"]
    assert frame.row(1, named=True)["adm2_code"] == "LA033"
    assert frame["location_selection_status"].to_list() == ["single_region"] * 3


def test_hourly_counts_uses_gdelt_seen_time(tmp_path: Path) -> None:
    output = tmp_path / "floods.parquet"
    clean_file(SAMPLE, output, "flood")
    columns, rows = hourly_counts(output)

    assert columns[-2:] == ["article_count", "unique_domain_count"]
    assert len(rows) == 3
    assert str(rows[0][0]).startswith("2026-08-19 12:00:00")


def test_official_headerless_gkg_zip_is_supported(tmp_path: Path) -> None:
    values = [""] * len(GKG_COLUMNS)
    sample_values = {
        "GKGRECORDID": "zip-001",
        "V2.1DATE": "20260819140000",
        "V2SOURCECOMMONNAME": "zip.test",
        "V2DOCUMENTIDENTIFIER": "https://zip.test/flood-report",
        "V2ENHANCEDTHEMES": "NATURAL_DISASTER_FLOOD,20",
        "V2ENHANCEDLOCATIONS": "4#Veracruz, Mexico#MX#MX30##19.17#-96.13#-1#10",
        "V1.5TONE": "-2.5,1.0,3.5",
    }
    for column, value in sample_values.items():
        values[GKG_COLUMNS.index(column)] = value

    archive_path = tmp_path / "sample.gkg.csv.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("sample.gkg.csv", "\t".join(values) + "\n")

    output = tmp_path / "from_zip.parquet"
    stats = clean_file(archive_path, output, "flood")
    assert stats.output_rows == 1
    assert pl.read_parquet(output).row(0, named=True)["record_id"] == "zip-001"


def test_zip_with_multiple_data_members_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "ambiguous.gkg.csv.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("first.gkg.csv", "one\n")
        archive.writestr("second.gkg.csv", "two\n")

    try:
        clean_file(archive_path, tmp_path / "ambiguous.parquet", "flood")
    except ValueError as error:
        assert "exactly one" in str(error)
    else:
        raise AssertionError("ZIP with multiple data members was accepted")


def test_clear_url_topic_mismatch_is_downgraded_and_auditable(tmp_path: Path) -> None:
    values = [""] * len(GKG_COLUMNS)
    sample_values = {
        "GKGRECORDID": "mismatch-001",
        "V2.1DATE": "20260820140000",
        "V2SOURCECOMMONNAME": "news.test",
        "V2DOCUMENTIDENTIFIER": (
            "https://news.test/article/astronomers-identify-new-black-hole-star-in-"
            "universe/73487469"
        ),
        "V2ENHANCEDTHEMES": "NATURAL_DISASTER_FLOOD,20",
        "V2ENHANCEDLOCATIONS": "4#New Jersey, United States#US#USNJ##40.05#-74.40#-1#10",
    }
    for column, value in sample_values.items():
        values[GKG_COLUMNS.index(column)] = value

    archive_path = tmp_path / "mismatch.gkg.csv.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("mismatch.gkg.csv", "\t".join(values) + "\n")

    output = tmp_path / "mismatch.parquet"
    stats = clean_file(
        archive_path, output, "flood", minimum_strength="weak"
    )
    row = pl.read_parquet(output).row(0, named=True)

    assert stats.url_topic_mismatch_rows == 1
    assert row["disaster_match_strength"] == "weak"
    assert row["url_topic_relevance"] == "mismatch"
    assert "url_topic_mismatch" in row["quality_flags"]


def test_opaque_url_uses_publisher_title_to_reject_unrelated_story(
    tmp_path: Path,
) -> None:
    values = [""] * len(GKG_COLUMNS)
    sample_values = {
        "GKGRECORDID": "title-mismatch-001",
        "V2.1DATE": "20260821140000",
        "V2SOURCECOMMONNAME": "news.test",
        "V2DOCUMENTIDENTIFIER": "https://news.test/node/2655431/media",
        "V2ENHANCEDTHEMES": "NATURAL_DISASTER_FLOOD,20",
        "V2ENHANCEDLOCATIONS": (
            "4#Dubai, United Arab Emirates#AE#AE03##25.26#55.30#-1#10"
        ),
    }
    for column, value in sample_values.items():
        values[GKG_COLUMNS.index(column)] = value

    archive_path = tmp_path / "opaque.gkg.csv.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("opaque.gkg.csv", "\t".join(values) + "\n")

    output = tmp_path / "opaque.parquet"
    stats = clean_file(
        archive_path,
        output,
        "flood",
        minimum_strength="weak",
        title_cache_path=tmp_path / "publisher-title-cache.json",
        title_fetcher=lambda _: (
            "TikTok bets on high-quality content as social media faces scrutiny"
        ),
    )
    row = pl.read_parquet(output).row(0, named=True)

    assert stats.publisher_title_checked_rows == 1
    assert stats.publisher_title_mismatch_rows == 1
    assert row["publisher_title_relevance"] == "mismatch"
    assert row["disaster_match_strength"] == "weak"
    assert "publisher_title_topic_mismatch" in row["quality_flags"]


def test_quality_report_summarizes_clean_data(tmp_path: Path) -> None:
    output = tmp_path / "floods.parquet"
    clean_file(SAMPLE, output, "flood")
    report = build_report(output, top=2)
    assert report["row_count"] == 3
    assert report["unique_domain_count"] == 3
    assert report["estimated_unique_story_count"] == 3
    assert report["invalid_coordinate_count"] == 1
    assert report["ambiguous_region_count"] == 0
    assert report["location_review_count"] == 0
    assert len(report["top_locations"]) == 2
