"""Print hourly location counts from a CrisisPulse silver Parquet file."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import duckdb


QUERY = """
SELECT
    date_trunc('hour', seen_at) AS window_start,
    disaster_type,
    coalesce(location_name, 'Unknown') AS location_name,
    coalesce(country_code, 'Unknown') AS country_code,
    count(*) AS article_count,
    count(DISTINCT source_domain) AS unique_domain_count
FROM read_parquet(?)
WHERE seen_at IS NOT NULL
GROUP BY ALL
ORDER BY window_start, article_count DESC, location_name
"""


def hourly_counts(parquet_path: Path) -> tuple[list[str], list[tuple[object, ...]]]:
    connection = duckdb.connect()
    try:
        result = connection.execute(QUERY, [str(parquet_path)])
        columns = [description[0] for description in result.description]
        return columns, result.fetchall()
    finally:
        connection.close()


def print_table(columns: list[str], rows: list[tuple[object, ...]]) -> None:
    values = [[str(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in values:
        widths = [max(width, len(value)) for width, value in zip(widths, row, strict=True)]
    print("  ".join(column.ljust(width) for column, width in zip(columns, widths, strict=True)))
    print("  ".join("-" * width for width in widths))
    for row in values:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths, strict=True)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="clean Parquet input")
    parser.add_argument("--csv", type=Path, help="optional CSV output")
    args = parser.parse_args()

    columns, rows = hourly_counts(args.input)
    print_table(columns, rows)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(rows)


if __name__ == "__main__":
    main()
