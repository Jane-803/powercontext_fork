from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mock_powercontext import MemoryStore  # noqa: E402


def test_scope_is_idempotent_and_persistent(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    first = store.scope("timeline-grudge-player-1", "Player 1")
    second = store.scope("timeline-grudge-player-1", "Player 1")
    assert first == second
    assert MemoryStore(path).scope("timeline-grudge-player-1", "Player 1") == first


def test_memory_is_isolated_and_recalled(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json")
    alice = store.scope("alice", "Alice")
    bob = store.scope("bob", "Bob")
    store.remember(alice, "alarm-clock dinosaurs")
    assert "dinosaurs" in store.prepare(alice, 3000)
    assert store.prepare(bob, 3000) is None


def test_saved_file_contains_auditable_artifact(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    scope = store.scope("player", "Player")
    record = store.remember(scope, "prank")
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert record["artifact_id"] == "memory-1"
    assert persisted["memories"][scope][0]["text"] == "prank"
