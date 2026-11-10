import pytest

from catalog import filter_places


PLACES = [
    {"name": "Far Favorite", "category": "park", "distance_m": 900, "rating": 4.9},
    {"name": "Near Okay", "category": "cafe", "distance_m": 100, "rating": 4.0},
    {"name": "Near Great", "category": "cafe", "distance_m": 200, "rating": 4.8},
    {"name": "Near Low", "category": "cafe", "distance_m": 150, "rating": 3.2},
]


def test_min_rating_can_be_combined_with_existing_filters() -> None:
    assert [place["name"] for place in filter_places(PLACES, category="cafe", max_distance_m=250, min_rating=4.5)] == [
        "Near Great"
    ]


@pytest.mark.parametrize("rating", [-0.1, 5.1])
def test_min_rating_rejects_values_outside_contract(rating: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 5"):
        filter_places(PLACES, min_rating=rating)


def test_existing_category_distance_and_order_behavior_is_unchanged() -> None:
    assert [place["name"] for place in filter_places(PLACES, category="cafe", max_distance_m=200)] == [
        "Near Okay",
        "Near Great",
        "Near Low",
    ]


def test_existing_negative_distance_validation_is_unchanged() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        filter_places(PLACES, max_distance_m=-1)
