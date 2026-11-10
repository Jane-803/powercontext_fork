from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_manifest(root: Path, manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for entry in manifest["sources"]:
        source = (root / entry["path"]).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file():
            raise ValueError(f"Invalid source path: {entry['path']}")
        content = source.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata = {
            "kind": entry["kind"],
            "logical_id": entry["logical_id"],
            "version": int(entry.get("version", 1)),
            "status": entry.get("status", "current"),
            "source": entry["path"],
            "sha256": digest,
        }
        record_id = f"{entry['logical_id']}@{metadata['version']}"
        records.append(
            {
                "record_id": record_id,
                "content": content,
                "metadata": metadata,
                "search_text": f"{entry.get('summary', '')}\n{entry['path']}\n{content}",
            }
        )
    return records


def select_effective(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest current version of each logical source, preserving DB ranking."""
    current_version: dict[str, int] = {}
    for record in records:
        metadata = record["metadata"]
        if metadata.get("status") == "current":
            logical_id = str(metadata["logical_id"])
            current_version[logical_id] = max(current_version.get(logical_id, 0), int(metadata["version"]))
    return [
        record
        for record in records
        if record["metadata"].get("status") == "current"
        and int(record["metadata"]["version"]) == current_version[str(record["metadata"]["logical_id"])]
    ]
