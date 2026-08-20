from pipelines.clean_gkg import classify_disaster, matches_disaster


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
