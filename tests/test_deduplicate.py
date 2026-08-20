from datetime import datetime

from pipelines.deduplicate import normalized_story_slug, story_group


def test_same_long_slug_in_same_window_groups_across_domains() -> None:
    first = "https://one.test/news/young-people-who-do-not-pass-gcse-english-and-maths"
    second = "https://two.test/2026/08/young-people-who-do-not-pass-gcse-english-and-maths.html"
    seen_at = datetime(2026, 8, 20, 14, 15)
    first_group = story_group(first, seen_at, "flood", "article-one")
    second_group = story_group(second, seen_at, "flood", "article-two")
    assert first_group == second_group
    assert first_group[1] == "url_slug_6h"


def test_short_generic_slug_falls_back_to_article_identity() -> None:
    assert normalized_story_slug("https://example.test/news/latest") is None
    group_id, method = story_group(
        "https://example.test/news/latest", datetime(2026, 8, 20, 14), "flood", "article-id"
    )
    assert group_id == "article-id"
    assert method == "canonical_url"
