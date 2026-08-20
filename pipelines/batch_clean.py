"""Clean a directory of GDELT GKG files into one deduplicated silver dataset."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from pipelines.clean_gkg import DISASTER_MARKERS, MATCH_STRENGTH, clean_files


def find_inputs(input_dir: Path, pattern: str) -> list[Path]:
    if not input_dir.is_dir():
        raise NotADirectoryError(input_dir)
    inputs = sorted(path for path in input_dir.glob(pattern) if path.is_file())
    if not inputs:
        raise FileNotFoundError(f"no files matching {pattern!r} in {input_dir}")
    return inputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--pattern", default="*.gkg.csv.zip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disaster", choices=sorted(DISASTER_MARKERS), default="flood")
    parser.add_argument(
        "--minimum-strength", choices=sorted(MATCH_STRENGTH), default="weak"
    )
    args = parser.parse_args()

    inputs = find_inputs(args.input_dir, args.pattern)
    stats = clean_files(inputs, args.output, args.disaster, args.minimum_strength)
    print(
        json.dumps(
            {
                **asdict(stats),
                "first_input": inputs[0].name,
                "last_input": inputs[-1].name,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
