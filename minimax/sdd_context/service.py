from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .corpus import load_manifest, select_effective
from .database import SeekDBStore
from .powercontext_store import PowerContextState


class ContextService:
    def __init__(self, root: Path, database: SeekDBStore | None = None, state: PowerContextState | None = None) -> None:
        self.root = root.resolve()
        self.database = database
        self.state = state or PowerContextState()

    def _database(self) -> SeekDBStore:
        if self.database is None:
            self.database = SeekDBStore(self.root / ".runtime" / "seekdb")
        return self.database

    def ingest(self, manifest: Path) -> int:
        records = load_manifest(self.root, manifest)
        self._database().upsert(records)
        return len(records)

    def context(self, task: str, limit: int = 20) -> dict[str, Any]:
        raw = self._database().query(task, limit=limit)
        selected = select_effective(raw)
        grouped: dict[str, list[dict[str, Any]]] = {"spec": [], "code": [], "test": [], "decision": []}
        for record in selected:
            item = {
                "record_id": record["record_id"],
                "source": record["metadata"]["source"],
                "logical_id": record["metadata"]["logical_id"],
                "version": record["metadata"]["version"],
                "distance": record["distance"],
                "content": record["content"],
            }
            grouped.setdefault(record["metadata"]["kind"], []).append(item)
        progress = self.state.load()
        return {
            "task": task,
            "selection_policy": "seekdb vector query, then newest current version per logical_id",
            "database_query": {"candidate_ids": [record["record_id"] for record in raw], "limit": limit},
            "sources": grouped,
            "task_state": progress,
        }

    def write_context(self, task: str, output: Path) -> dict[str, Any]:
        context = self.context(task)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as context_file:
            context_file.write(json.dumps(context, ensure_ascii=False, indent=2) + "\n")
        return context
