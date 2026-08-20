from pipelines.parse_locations import (
    choose_primary_location,
    distinct_location_count,
    parse_enhanced_locations,
)


def test_parser_prefers_valid_city_location() -> None:
    raw = (
        "1#United States#US#US##38.0#-97.0#US#10;"
        "3#Baton Rouge, Louisiana, United States#US#USLA#LA033#30.4515#-91.1871#-1#40"
    )
    locations = parse_enhanced_locations(raw)
    primary = choose_primary_location(locations)
    assert len(locations) == 2
    assert primary is not None
    assert primary.name == "Baton Rouge, Louisiana, United States"
    assert primary.adm2_code == "LA033"
    assert primary.valid_coordinates is True


def test_parser_preserves_invalid_coordinates_for_quality_flags() -> None:
    locations = parse_enhanced_locations("2#Unknown#US#USXX##125#-190#-1#20")
    assert len(locations) == 1
    assert locations[0].latitude == 125
    assert locations[0].valid_coordinates is False


def test_repeated_mentions_are_one_distinct_location_and_influence_primary() -> None:
    raw = (
        "3#Edgewater, Colorado, United States#US#USCO#CO059#39.753#-105.064#202848#10;"
        "3#Denver, Colorado, United States#US#USCO#CO031#39.7392#-104.985#201738#20;"
        "3#Denver, Colorado, United States#US#USCO#CO031#39.7392#-104.985#201738#80"
    )
    locations = parse_enhanced_locations(raw)
    primary = choose_primary_location(locations)
    assert distinct_location_count(locations) == 2
    assert primary is not None
    assert primary.name == "Denver, Colorado, United States"
