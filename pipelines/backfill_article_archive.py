"""Backfill the permanent article archive from every retained raw GDELT ZIP."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from pipelines.batch_clean import find_inputs
from pipelines.clean_gkg import clean_files
from pipelines.merge_article_archive import merge_article_archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--title-cache", type=Path)
    parser.add_argument("--pattern", default="*.gkg.csv.zip")
    args = parser.parse_args()

    inputs = find_inputs(args.raw_dir, args.pattern)
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=args.archive.parent,
            prefix="article-backfill.",
            suffix=".parquet.partial",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        clean_stats = clean_files(
            inputs,
            temporary_path,
            disaster_type="flood",
            minimum_strength="weak",
            title_cache_path=args.title_cache,
        )
        archive_stats = merge_article_archive(temporary_path, args.archive)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print(
        json.dumps(
            {
                "retained_raw_files_processed": len(inputs),
                "first_input": inputs[0].name,
                "last_input": inputs[-1].name,
                "clean": asdict(clean_stats),
                "archive": asdict(archive_stats),
                "archive_path": str(args.archive),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
