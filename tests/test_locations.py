from pipelines.parse_locations import (
    choose_primary_location,
    distinct_location_count,
    parse_enhanced_locations,
    select_primary_location,
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


def test_tied_regions_are_marked_ambiguous_even_when_one_location_is_selected() -> None:
    raw = (
        "3#Big Island, New Hampshire, United States#US#USNH#NH007#43.7#-71.6#1#5;"
        "3#Hawaii, United States#US#USHI##19.9#-155.6#2#20"
    )
    selection = select_primary_location(parse_enhanced_locations(raw))

    assert selection.location is not None
    assert selection.location.adm1_code == "USNH"
    assert selection.status == "ambiguous_region"
    assert selection.candidate_regions == ("US:USHI", "US:USNH")


def test_repeated_region_mentions_create_a_dominant_assignment() -> None:
    raw = (
        "3#Big Island, New Hampshire, United States#US#USNH#NH007#43.7#-71.6#1#5;"
        "3#Hawaii, United States#US#USHI##19.9#-155.6#2#20;"
        "3#Hawaii, United States#US#USHI##19.9#-155.6#2#80"
    )
    selection = select_primary_location(parse_enhanced_locations(raw))

    assert selection.location is not None
    assert selection.location.adm1_code == "USHI"
    assert selection.status == "dominant_region"
    assert selection.candidate_regions == ("US:USHI", "US:USNH")
