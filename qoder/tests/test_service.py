import json

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


def make_paper(**overrides):
    paper = {
        "id": "x",
        "title": "T",
        "authors": "A",
        "year": 2024,
        "abstract": "Z",
        "source": "https://example.com/x",
    }
    paper.update(overrides)
    return paper


def write_source(tmp_path, payload):
    source = tmp_path / "papers.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source


def test_import_and_search_use_store(tmp_path):
    source = write_source(tmp_path, {"papers": [make_paper()]})
    store = FakeStore()
    service = PaperTrailService(store)
    assert service.import_file(source) == 1
    result = service.search({"query": "long context", "year_from": 2020, "limit": 3})
    assert store.last_query == ("long context", 3, 2020)
    assert result["engine"] == "seekdb vector search + structured year filter"
    assert result["results"][0]["id"] == "p4"


def test_import_rejects_invalid_json(tmp_path):
    source = tmp_path / "papers.json"
    source.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="is not valid JSON"):
        PaperTrailService(FakeStore()).import_file(source)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "must contain a JSON object"),
        ({"papers": {}}, "must contain a 'papers' list"),
        ({"papers": ["not an object"]}, "paper 0 must be a JSON object"),
        ({"papers": [{"id": "x"}]}, "paper 0 misses:"),
        ({"papers": [make_paper(year="recent")]}, "field 'year' must be an integer"),
        ({"papers": [make_paper(tags="RAG")]}, "field 'tags' must be a list of strings"),
        ({"papers": [make_paper(), make_paper()]}, "duplicates id 'x'"),
    ],
)
def test_import_rejects_malformed_papers(tmp_path, payload, message):
    source = write_source(tmp_path, payload)
    with pytest.raises(ValueError, match=message):
        PaperTrailService(FakeStore()).import_file(source)


def test_import_validates_every_paper_before_writing(tmp_path):
    source = write_source(tmp_path, {"papers": [make_paper(), make_paper(id="y", year="recent")]})
    store = FakeStore()
    with pytest.raises(ValueError, match="paper 1 field 'year'"):
        PaperTrailService(store).import_file(source)
    assert store.papers == []


def test_search_rejects_empty_query():
    with pytest.raises(ValueError, match="must not be empty"):
        PaperTrailService(FakeStore()).search({"query": "  "})


@pytest.mark.parametrize(
    ("request_payload", "message"),
    [
        ({"query": 42}, "query must be a string"),
        ({"query": "retrieval", "limit": "many"}, "limit must be an integer"),
        ({"query": "retrieval", "limit": 2.5}, "limit must be an integer"),
        ({"query": "retrieval", "year_from": True}, "year_from must be an integer"),
        ({"query": "retrieval", "year_from": 2020.5}, "year_from must be an integer"),
        ({"query": "retrieval", "year_from": "20x0"}, "year_from must be an integer"),
    ],
)
def test_search_rejects_invalid_parameters(request_payload, message):
    with pytest.raises(ValueError, match=message):
        PaperTrailService(FakeStore()).search(request_payload)


def test_search_accepts_numeric_strings_and_null_defaults():
    store = FakeStore()
    service = PaperTrailService(store)
    service.search({"query": "retrieval", "limit": "3", "year_from": "2020"})
    assert store.last_query == ("retrieval", 3, 2020)
    service.search({"query": "retrieval", "limit": None, "year_from": None})
    assert store.last_query == ("retrieval", 5, None)


def test_search_limits_requested_result_count():
    store = FakeStore()
    PaperTrailService(store).search({"query": "retrieval", "limit": 999})
    assert store.last_query[1] == 10
