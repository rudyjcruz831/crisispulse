import json
from pathlib import Path

import pytest

from pipelines.publisher_title_overrides import load_publisher_title_overrides


def test_loads_audited_title_overrides(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "url": "https://news.example/story/1",
                        "title": "Flooding closes roads across the county",
                        "verified_on": "2026-08-24",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_publisher_title_overrides(path) == {
        "https://news.example/story/1": "Flooding closes roads across the county"
    }


@pytest.mark.parametrize(
    ("url", "title"),
    [
        ("http://localhost/story", "Flooding closes roads across the county"),
        ("https://news.example/story", "Title of the Page"),
    ],
)
def test_rejects_unsafe_or_untrustworthy_overrides(
    tmp_path: Path,
    url: str,
    title: str,
) -> None:
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [{"url": url, "title": title}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="override 0 is invalid"):
        load_publisher_title_overrides(path)
