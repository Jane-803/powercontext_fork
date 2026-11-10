from pathlib import Path

from sdd_context.service import ContextService


class FakeDatabase:
    def __init__(self) -> None:
        self.records = []

    def upsert(self, records: list[dict]) -> None:
        self.records.extend(records)

    def query(self, task: str, limit: int = 20) -> list[dict]:
        return [
            {"record_id": item["record_id"], "content": item["content"], "metadata": item["metadata"], "distance": 0.1}
            for item in reversed(self.records[-limit:])
        ]


class FakeState:
    def load(self) -> dict:
        return {"revision": 2, "objective": "resume work"}


def test_reimport_uses_updated_spec_and_exposes_real_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    database = FakeDatabase()
    service = ContextService(root, database=database, state=FakeState())
    service.ingest(root / "corpus" / "initial.json")
    service.ingest(root / "corpus" / "update-v2.json")

    context = service.context("add min_rating while preserving distance and order")

    specs = context["sources"]["spec"]
    assert [item["version"] for item in specs] == [2]
    assert specs[0]["source"] == "specs/place-filter-v2.md"
    assert "min_rating" in specs[0]["content"]
    assert context["sources"]["code"][0]["source"] == "snapshots/before/catalog.py"
    assert context["sources"]["test"][0]["source"] == "tests/test_catalog.py"
    assert context["task_state"]["revision"] == 2
    assert context["database_query"]["candidate_ids"]
