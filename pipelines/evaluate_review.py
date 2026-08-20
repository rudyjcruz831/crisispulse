"""Score completed human labels in a CrisisPulse manual-review CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED_COLUMNS = {
    "disaster_match_strength",
    "location_selection_status",
    "country_code",
    "adm1_code",
    "label_disaster_relevance",
    "label_primary_region",
}
CONFIDENT_LOCATION_STATUSES = {"single_region", "dominant_region"}
RELEVANCE_LABELS = {"relevant", "not_relevant", "uncertain", ""}


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _machine_region(row: dict[str, str]) -> str:
    if row["location_selection_status"] not in CONFIDENT_LOCATION_STATUSES:
        return "UNKNOWN"
    country_code = row["country_code"].strip().upper()
    adm1_code = row["adm1_code"].strip().upper()
    if country_code and adm1_code:
        return f"{country_code}:{adm1_code}"
    return country_code or "UNKNOWN"


def evaluate_review(input_path: Path) -> dict[str, object]:
    with input_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"review CSV is missing columns: {sorted(missing)}")
        rows = list(reader)

    relevance_unlabeled = 0
    relevance_uncertain = 0
    relevance_by_strength: dict[str, dict[str, int]] = {}
    location_unlabeled = 0
    location_uncertain = 0
    location_labeled = 0
    location_correct = 0

    for row_number, row in enumerate(rows, start=2):
        relevance = row["label_disaster_relevance"].strip().lower()
        if relevance not in RELEVANCE_LABELS:
            raise ValueError(
                f"row {row_number} has unsupported disaster relevance label: {relevance!r}"
            )
        if not relevance:
            relevance_unlabeled += 1
        elif relevance == "uncertain":
            relevance_uncertain += 1
        else:
            strength = row["disaster_match_strength"].strip().lower()
            counts = relevance_by_strength.setdefault(
                strength, {"labeled": 0, "relevant": 0}
            )
            counts["labeled"] += 1
            counts["relevant"] += int(relevance == "relevant")

        primary_region = row["label_primary_region"].strip().upper()
        if not primary_region:
            location_unlabeled += 1
        elif primary_region == "UNCERTAIN":
            location_uncertain += 1
        else:
            location_labeled += 1
            location_correct += int(primary_region == _machine_region(row))

    strength_results = {
        strength: {
            **counts,
            "relevance_rate": _rate(counts["relevant"], counts["labeled"]),
        }
        for strength, counts in sorted(relevance_by_strength.items())
    }
    relevance_labeled = sum(
        counts["labeled"] for counts in relevance_by_strength.values()
    )
    relevance_relevant = sum(
        counts["relevant"] for counts in relevance_by_strength.values()
    )
    return {
        "input": str(input_path),
        "review_rows": len(rows),
        "relevance": {
            "labeled_rows": relevance_labeled,
            "unlabeled_rows": relevance_unlabeled,
            "uncertain_rows": relevance_uncertain,
            "relevant_rows": relevance_relevant,
            "overall_relevance_rate": _rate(
                relevance_relevant, relevance_labeled
            ),
            "by_match_strength": strength_results,
        },
        "primary_region": {
            "labeled_rows": location_labeled,
            "unlabeled_rows": location_unlabeled,
            "uncertain_rows": location_uncertain,
            "correct_rows": location_correct,
            "accuracy": _rate(location_correct, location_labeled),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_review(args.input)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
