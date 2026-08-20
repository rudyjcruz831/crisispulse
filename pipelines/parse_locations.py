"""Parse GDELT's V2ENHANCEDLOCATIONS field."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GDELTLocation:
    location_type: int | None
    name: str | None
    country_code: str | None
    adm1_code: str | None
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
        fields.extend([""] * (8 - len(fields)))
        latitude = _number(fields[4])
        longitude = _number(fields[5])
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
                latitude=latitude,
                longitude=longitude,
                feature_id=fields[6].strip() or None,
                character_offset=_integer(fields[7]),
                valid_coordinates=valid_coordinates,
            )
        )
    return locations


def choose_primary_location(locations: list[GDELTLocation]) -> GDELTLocation | None:
    """Prefer a geocoded city, then a state/region, then a country."""
    if not locations:
        return None
    specificity = {3: 4, 4: 4, 2: 3, 5: 3, 1: 2}
    return max(
        locations,
        key=lambda location: (
            int(location.valid_coordinates),
            specificity.get(location.location_type, 1),
            int(bool(location.name)),
        ),
    )
