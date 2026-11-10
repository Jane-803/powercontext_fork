import pytest

from papertrail.service import PaperTrailService


class FakeStore:
    def __init__(self) -> None:
        self.papers = []
        self.last_query = None

    def upsert(self, papers):
        self.papers = papers
        return len(papers)

    def search(self, query, limit, year_from):
        self.last_query = (query, limit, year_from)
        return [{"id": "p4", "title": "Lost in the Middle", "year": 2023, "score": 0.91}]


def test_import_and_search_use_store(tmp_path):
    source = tmp_path / "papers.json"
    source.write_text('{"papers":[{"id":"x","title":"T","authors":"A","year":2024,"abstract":"Z","source":"url"}]}')
    store = FakeStore()
    service = PaperTrailService(store)
    assert service.import_file(source) == 1
    result = service.search({"query": "long context", "year_from": 2020, "limit": 3})
    assert store.last_query == ("long context", 3, 2020)
    assert result["engine"] == "seekdb vector search + structured year filter"
    assert result["results"][0]["id"] == "p4"


def test_search_rejects_empty_query():
    with pytest.raises(ValueError, match="must not be empty"):
        PaperTrailService(FakeStore()).search({"query": "  "})


def test_search_limits_requested_result_count():
    store = FakeStore()
    PaperTrailService(store).search({"query": "retrieval", "limit": 999})
    assert store.last_query[1] == 10
