from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .store import PaperStore

REQUIRED_PAPER_FIELDS = ("id", "title", "authors", "year", "abstract", "source")
INTEGER_TEXT = re.compile(r"[+-]?\d+")


def _parse_integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and INTEGER_TEXT.fullmatch(value.strip()):
        return int(value)
    raise ValueError(f"{field} must be an integer")


def _optional_integer(value: Any, field: str) -> int | None:
    return None if value is None or value == "" else _parse_integer(value, field)


def _require_text(paper: dict[str, Any], field: str, index: int) -> str:
    value = paper[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"paper {index} field '{field}' must be a non-empty string")
    return value


class PaperTrailService:
    def __init__(self, store: PaperStore) -> None:
        self.store = store

    def import_file(self, source: Path) -> int:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source.name} is not valid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{source.name} must contain a JSON object")
        papers = payload.get("papers")
        if not isinstance(papers, list):
            raise ValueError(f"{source.name} must contain a 'papers' list")
        seen_ids: set[str] = set()
        for index, paper in enumerate(papers):
            if not isinstance(paper, dict):
                raise ValueError(f"paper {index} must be a JSON object")
            missing = set(REQUIRED_PAPER_FIELDS) - paper.keys()
            if missing:
                raise ValueError(f"paper {index} misses: {', '.join(sorted(missing))}")
            paper_id = _require_text(paper, "id", index)
            if paper_id in seen_ids:
                raise ValueError(f"paper {index} duplicates id '{paper_id}'")
            seen_ids.add(paper_id)
            for field in ("title", "authors", "abstract", "source"):
                _require_text(paper, field, index)
            _parse_integer(paper["year"], f"paper {index} field 'year'")
            tags = paper.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise ValueError(f"paper {index} field 'tags' must be a list of strings")
            status = paper.get("status", "unread")
            if not isinstance(status, str):
                raise ValueError(f"paper {index} field 'status' must be a string")
        return self.store.upsert(papers)

    def search(self, request: dict[str, Any]) -> dict[str, Any]:
        query_value = request.get("query", "")
        if not isinstance(query_value, str):
            raise ValueError("query must be a string")
        query = query_value.strip()
        if not query:
            raise ValueError("query must not be empty")
        limit_value = request.get("limit", 5)
        limit = 5 if limit_value is None or limit_value == "" else _parse_integer(limit_value, "limit")
        limit = max(1, min(limit, 10))
        year_from = _optional_integer(request.get("year_from"), "year_from")
        results = self.store.search(query, limit, year_from)
        return {
            "query": query,
            "filters": {"year_from": year_from},
            "engine": "seekdb vector search + structured year filter",
            "result_count": len(results),
            "results": results,
        }
