"""Parse GDELT's V2ENHANCEDLOCATIONS field."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GDELTLocation:
    location_type: int | None
    name: str | None
    country_code: str | None
    adm1_code: str | None
    adm2_code: str | None
    latitude: float | None
    longitude: float | None
    feature_id: str | None
    character_offset: int | None
    valid_coordinates: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _integer(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_enhanced_locations(raw_value: str | None) -> list[GDELTLocation]:
    """Parse valid-looking location entries without discarding questionable coordinates."""
    if not raw_value:
        return []

    locations: list[GDELTLocation] = []
    for entry in raw_value.split(";"):
        if not entry.strip():
            continue
        fields = entry.split("#")
        # Live GKG 2.1 data contains nine fields:
        # type, name, country, ADM1, ADM2, latitude, longitude, feature ID,
        # and character offset.
        fields.extend([""] * (9 - len(fields)))
        latitude = _number(fields[5])
        longitude = _number(fields[6])
        valid_coordinates = (
            latitude is not None
            and longitude is not None
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        )
        locations.append(
            GDELTLocation(
                location_type=_integer(fields[0]),
                name=fields[1].strip() or None,
                country_code=fields[2].strip().upper() or None,
                adm1_code=fields[3].strip().upper() or None,
                adm2_code=fields[4].strip().upper() or None,
                latitude=latitude,
                longitude=longitude,
                feature_id=fields[7].strip() or None,
                character_offset=_integer(fields[8]),
                valid_coordinates=valid_coordinates,
            )
        )
    return locations


def location_key(location: GDELTLocation) -> tuple[object, ...]:
    """Identify the same place across repeated mentions in one article."""
    return (
        location.location_type,
        location.name,
        location.country_code,
        location.adm1_code,
        location.adm2_code,
        location.latitude,
        location.longitude,
        location.feature_id,
    )


def distinct_location_count(locations: list[GDELTLocation]) -> int:
    return len({location_key(location) for location in locations})


def choose_primary_location(locations: list[GDELTLocation]) -> GDELTLocation | None:
    """Prefer a valid, specific, frequently mentioned, early location."""
    if not locations:
        return None

    counts: dict[tuple[object, ...], int] = {}
    representatives: dict[tuple[object, ...], GDELTLocation] = {}
    for location in locations:
        key = location_key(location)
        counts[key] = counts.get(key, 0) + 1
        current = representatives.get(key)
        current_offset = current.character_offset if current else None
        if current is None or (
            location.character_offset is not None
            and (current_offset is None or location.character_offset < current_offset)
        ):
            representatives[key] = location

    specificity = {3: 4, 4: 4, 2: 3, 5: 3, 1: 2}
    return max(
        representatives.values(),
        key=lambda location: (
            int(location.valid_coordinates),
            specificity.get(location.location_type, 1),
            counts[location_key(location)],
            int(bool(location.name)),
            -(location.character_offset if location.character_offset is not None else 10**12),
        ),
    )
