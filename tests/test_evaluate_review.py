import csv
from pathlib import Path

from pipelines.evaluate_review import evaluate_review


def test_review_evaluation_excludes_uncertain_labels(tmp_path: Path) -> None:
    review_path = tmp_path / "review.csv"
    fieldnames = [
        "disaster_match_strength",
        "location_selection_status",
        "country_code",
        "adm1_code",
        "label_disaster_relevance",
        "label_primary_region",
    ]
    rows = [
        ["high", "single_region", "US", "USHI", "relevant", "US:USHI"],
        ["high", "ambiguous_region", "US", "USNH", "relevant", "US:USHI"],
        ["weak", "missing", "", "", "not_relevant", "UNKNOWN"],
        ["weak", "dominant_region", "UK", "UK", "relevant", "uncertain"],
    ]
    with review_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fieldnames)
        writer.writerows(rows)

    report = evaluate_review(review_path)

    assert report["relevance"]["overall_relevance_rate"] == 0.75
    assert report["relevance"]["by_match_strength"]["high"]["relevance_rate"] == 1
    assert report["relevance"]["by_match_strength"]["weak"]["relevance_rate"] == 0.5
    assert report["primary_region"]["labeled_rows"] == 3
    assert report["primary_region"]["uncertain_rows"] == 1
    assert report["primary_region"]["accuracy"] == 2 / 3
