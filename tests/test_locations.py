from pipelines.parse_locations import choose_primary_location, parse_enhanced_locations


def test_parser_prefers_valid_city_location() -> None:
    raw = (
        "1#United States#US#US#38.0#-97.0#US#10;"
        "3#Baton Rouge, Louisiana, United States#US#USLA#30.4515#-91.1871#-1#40"
    )
    locations = parse_enhanced_locations(raw)
    primary = choose_primary_location(locations)
    assert len(locations) == 2
    assert primary is not None
    assert primary.name == "Baton Rouge, Louisiana, United States"
    assert primary.valid_coordinates is True


def test_parser_preserves_invalid_coordinates_for_quality_flags() -> None:
    locations = parse_enhanced_locations("2#Unknown#US#USXX#125#-190#-1#20")
    assert len(locations) == 1
    assert locations[0].latitude == 125
    assert locations[0].valid_coordinates is False
