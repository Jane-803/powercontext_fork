from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sdd_context.database import MAX_VECTOR_QUERY_ATTEMPTS, SeekDBStore
from sdd_context.embedding import DIMENSION, embed


class FakeCollection:
    def __init__(self) -> None:
        self.upsert_call = None
        self.query_call = None

    def upsert(self, **kwargs) -> None:
        self.upsert_call = kwargs

    def query(self, **kwargs) -> dict:
        self.query_call = kwargs
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def count(self) -> int:
        return 0


def test_embedded_store_creates_database_before_client_and_uses_local_vector_dimension(
    monkeypatch, tmp_path: Path
) -> None:
    events = []
    collection = FakeCollection()

    class Admin:
        def __init__(self, **kwargs) -> None:
            events.append(("admin", kwargs))

        def list_databases(self):
            events.append(("list_databases",))
            return [SimpleNamespace(name="mysql")]

        def create_database(self, name):
            events.append(("create_database", name))

    class Client:
        def __init__(self, **kwargs) -> None:
            events.append(("client", kwargs))

        def get_or_create_collection(self, name, **kwargs):
            events.append(("collection", name, kwargs))
            return collection

    class HNSWConfiguration:
        def __init__(self, *, dimension):
            self.dimension = dimension

    monkeypatch.delenv("SEEKDB_HOST", raising=False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "pyseekdb",
        SimpleNamespace(AdminClient=Admin, Client=Client, HNSWConfiguration=HNSWConfiguration),
    )

    store = SeekDBStore(tmp_path / "seekdb")

    assert events[1:4] == [("list_databases",), ("create_database", "sdd_context"),
                           ("client", {"path": str(tmp_path / "seekdb"), "database": "sdd_context"})]
    _, _, options = events[-1]
    assert options["configuration"].dimension == DIMENSION
    assert options["embedding_function"] is None
    store.upsert([{"record_id": "r1", "search_text": "alpha", "content": "alpha", "metadata": {}}])
    assert len(collection.upsert_call["embeddings"][0]) == DIMENSION
    store.query("alpha")
    assert len(collection.query_call["query_embeddings"]) == DIMENSION
    assert len(embed("alpha")) == DIMENSION


def test_embedded_store_does_not_recreate_existing_database(monkeypatch, tmp_path: Path) -> None:
    events = []

    class Admin:
        def __init__(self, **kwargs) -> None:
            pass

        def list_databases(self):
            return [SimpleNamespace(name="sdd_context")]

        def create_database(self, name):
            events.append(name)

    class Client:
        def __init__(self, **kwargs) -> None:
            pass

        def get_or_create_collection(self, name, **kwargs):
            return object()

    class HNSWConfiguration:
        def __init__(self, *, dimension):
            self.dimension = dimension

    monkeypatch.delenv("SEEKDB_HOST", raising=False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "pyseekdb",
        SimpleNamespace(AdminClient=Admin, Client=Client, HNSWConfiguration=HNSWConfiguration),
    )
    SeekDBStore(tmp_path / "seekdb")
    assert events == []


def test_query_retries_lazy_hnsw_empty_reads_for_nonempty_collection() -> None:
    collection = FakeCollection()
    collection.count = lambda: 1
    calls = 0

    def query(**kwargs):
        nonlocal calls
        calls += 1
        if calls < MAX_VECTOR_QUERY_ATTEMPTS:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        return {
            "ids": [["r1"]],
            "documents": [["alpha"]],
            "metadatas": [[{"kind": "spec"}]],
            "distances": [[0.0]],
        }

    collection.query = query
    store = object.__new__(SeekDBStore)
    store._collection = collection

    assert store.query("alpha") == [
        {"record_id": "r1", "content": "alpha", "metadata": {"kind": "spec"}, "distance": 0.0}
    ]
    assert calls == MAX_VECTOR_QUERY_ATTEMPTS


def test_query_does_not_retry_an_empty_collection() -> None:
    collection = FakeCollection()
    calls = 0

    def query(**kwargs):
        nonlocal calls
        calls += 1
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    collection.query = query
    store = object.__new__(SeekDBStore)
    store._collection = collection

    assert store.query("alpha") == []
    assert calls == 1
