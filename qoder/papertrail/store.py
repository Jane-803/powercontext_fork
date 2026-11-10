from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .embedding import embed


class PaperStore:
    """All paper persistence and semantic retrieval runs through seekdb."""

    def __init__(self, path: Path) -> None:
        try:
            import pyseekdb
        except (ImportError, OSError) as exc:
            raise RuntimeError("pyseekdb is required; use Linux embedded mode or configure SEEKDB_HOST") from exc
        if host := os.getenv("SEEKDB_HOST"):
            self.client = pyseekdb.Client(
                host=host,
                port=int(os.getenv("SEEKDB_PORT", "2881")),
                tenant=os.getenv("SEEKDB_TENANT", "sys"),
                database=os.getenv("SEEKDB_DATABASE", "test"),
                user=os.getenv("SEEKDB_USER", "root"),
                password=os.getenv("SEEKDB_PASSWORD", ""),
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.client = pyseekdb.Client(path=str(path), database="papertrail")
        self.collection = self.client.get_or_create_collection("research_materials")

    def upsert(self, papers: list[dict[str, Any]]) -> int:
        self.collection.upsert(
            ids=[paper["id"] for paper in papers],
            embeddings=[embed(self._search_text(paper)) for paper in papers],
            documents=[paper["abstract"] for paper in papers],
            metadatas=[
                {
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "year": int(paper["year"]),
                    "tags": ",".join(paper.get("tags", [])),
                    "source": paper["source"],
                    "status": paper.get("status", "unread"),
                }
                for paper in papers
            ],
        )
        return len(papers)

    def search(self, query: str, limit: int = 5, year_from: int | None = None) -> list[dict[str, Any]]:
        where = {"year": {"$gte": year_from}} if year_from else None
        result = self.collection.query(
            query_embeddings=embed(query),
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {"id": id_, "abstract": document, "score": round(1 / (1 + float(distance)), 4), **metadata}
            for id_, document, metadata, distance in zip(ids, documents, metadatas, distances, strict=True)
        ]

    @staticmethod
    def _search_text(paper: dict[str, Any]) -> str:
        return " ".join([paper["title"], paper["abstract"], " ".join(paper.get("tags", []))])
