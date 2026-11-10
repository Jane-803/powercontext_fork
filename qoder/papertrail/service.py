from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import PaperStore


class PaperTrailService:
    def __init__(self, store: PaperStore) -> None:
        self.store = store

    def import_file(self, source: Path) -> int:
        payload = json.loads(source.read_text(encoding="utf-8"))
        papers = payload["papers"]
        required = {"id", "title", "authors", "year", "abstract", "source"}
        for index, paper in enumerate(papers):
            missing = required - paper.keys()
            if missing:
                raise ValueError(f"paper {index} misses: {', '.join(sorted(missing))}")
        return self.store.upsert(papers)

    def search(self, request: dict[str, Any]) -> dict[str, Any]:
        query = str(request.get("query", "")).strip()
        if not query:
            raise ValueError("query must not be empty")
        limit = max(1, min(int(request.get("limit", 5)), 10))
        year_from = int(request["year_from"]) if request.get("year_from") else None
        results = self.store.search(query, limit, year_from)
        return {
            "query": query,
            "filters": {"year_from": year_from},
            "engine": "seekdb vector search + structured year filter",
            "result_count": len(results),
            "results": results,
        }
