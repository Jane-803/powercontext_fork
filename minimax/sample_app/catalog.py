from __future__ import annotations

from typing import TypedDict


class Place(TypedDict):
    name: str
    category: str
    distance_m: int
    rating: float


def filter_places(
    places: list[Place],
    *,
    category: str | None = None,
    max_distance_m: int | None = None,
    min_rating: float | None = None,
) -> list[Place]:
    """Return matching places without reordering the caller's list."""
    if max_distance_m is not None and max_distance_m < 0:
        raise ValueError("max_distance_m must be non-negative")
    if min_rating is not None and not 0 <= min_rating <= 5:
        raise ValueError("min_rating must be between 0 and 5")
    return [
        place
        for place in places
        if (category is None or place["category"] == category)
        and (max_distance_m is None or place["distance_m"] <= max_distance_m)
        and (min_rating is None or place["rating"] >= min_rating)
    ]
