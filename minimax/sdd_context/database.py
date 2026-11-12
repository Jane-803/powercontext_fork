from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .embedding import DIMENSION, embed

MAX_VECTOR_QUERY_ATTEMPTS = 4


class SeekDBStore:
    """Thin adapter that keeps all engineering material and retrieval in seekdb."""

    def __init__(self, path: Path, collection_name: str = "engineering_context") -> None:
        try:
            import pyseekdb
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                "pyseekdb embedded mode is required. Run this sample on Linux/macOS or configure a seekdb server."
            ) from exc
        host = os.getenv("SEEKDB_HOST")
        if host:
            client = pyseekdb.Client(
                host=host,
                port=int(os.getenv("SEEKDB_PORT", "2881")),
                tenant=os.getenv("SEEKDB_TENANT", "sys"),
                database=os.getenv("SEEKDB_DATABASE", "test"),
                user=os.getenv("SEEKDB_USER", "root"),
                password=os.getenv("SEEKDB_PASSWORD", ""),
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            admin = pyseekdb.AdminClient(path=str(path))
            if not any(database.name == "sdd_context" for database in admin.list_databases()):
                admin.create_database("sdd_context")
            client = pyseekdb.Client(path=str(path), database="sdd_context")
        self._client = client
        self._collection = client.get_or_create_collection(
            collection_name,
            configuration=pyseekdb.HNSWConfiguration(dimension=DIMENSION),
            embedding_function=None,
        )
        if self._collection.dimension != DIMENSION:
            raise ValueError(
                f"Collection {collection_name!r} has vector dimension {self._collection.dimension}; "
                f"this application requires {DIMENSION}. Delete the incompatible collection and ingest again."
            )

    def upsert(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        self._collection.upsert(
            ids=[record["record_id"] for record in records],
            embeddings=[embed(record["search_text"]) for record in records],
            documents=[record["content"] for record in records],
            metadatas=[record["metadata"] for record in records],
        )

    def query(self, task: str, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        query_embedding = embed(task)
        for attempt in range(MAX_VECTOR_QUERY_ATTEMPTS):
            result = self._collection.query(
                query_embeddings=query_embedding,
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )
            ids = (result.get("ids") or [[]])[0]
            if ids or attempt == MAX_VECTOR_QUERY_ATTEMPTS - 1 or self._collection.count() == 0:
                break
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {"record_id": record_id, "content": document, "metadata": metadata, "distance": distance}
            for record_id, document, metadata, distance in zip(ids, documents, metadatas, distances, strict=True)
        ]

    def count(self) -> int:
        return self._collection.count()
