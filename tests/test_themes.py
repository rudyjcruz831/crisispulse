from pipelines.clean_gkg import classify_disaster, matches_disaster, url_topic_relevance


def test_explicit_flood_theme_is_high_confidence() -> None:
    strength, matched = classify_disaster(["NATURAL_DISASTER_FLOODING"], "flood")
    assert strength == "high"
    assert matched == ["NATURAL_DISASTER_FLOODING"]


def test_flooded_only_theme_is_weak_but_auditable() -> None:
    themes = ["NATURAL_DISASTER_FLOODED"]
    assert matches_disaster(themes, "flood") is False
    assert matches_disaster(themes, "flood", minimum_strength="weak") is True


def test_world_bank_policy_theme_is_not_a_high_confidence_event() -> None:
    strength, _ = classify_disaster(["WB_154_FLOOD_PROTECTION"], "flood")
    assert strength == "weak"


def test_url_headline_supports_flood_topic_before_trailing_numeric_id() -> None:
    url = "https://news.test/article/flash-flood-warning-issued-for-county/73487469"
    assert url_topic_relevance(url, "flood") == "supporting"


def test_url_headline_flags_clear_topic_mismatch() -> None:
    url = (
        "https://news.test/article/astronomers-identify-new-black-hole-star-in-"
        "universe/73487469"
    )
    assert url_topic_relevance(url, "flood") == "mismatch"


def test_opaque_url_does_not_overrule_gdelt_topic() -> None:
    url = "https://news.test/article/82e79df0-cf53-505d-a1d0-10a9ef4bf9d6"
    assert url_topic_relevance(url, "flood") == "unknown"
