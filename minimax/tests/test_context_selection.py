from sdd_context.corpus import select_effective


def record(record_id: str, logical_id: str, version: int, status: str = "current") -> dict:
    return {
        "record_id": record_id,
        "content": record_id,
        "distance": 0.1,
        "metadata": {"logical_id": logical_id, "version": version, "status": status},
    }


def test_newest_current_spec_replaces_stale_version_without_hiding_other_sources() -> None:
    records = [
        record("spec@1", "place-filter", 1),
        record("code@1", "catalog", 1),
        record("spec@2", "place-filter", 2),
        record("test@1", "catalog-tests", 1),
    ]
    assert [item["record_id"] for item in select_effective(records)] == ["code@1", "spec@2", "test@1"]


def test_superseded_records_are_not_selected() -> None:
    assert select_effective([record("old", "spec", 1, "superseded")]) == []
