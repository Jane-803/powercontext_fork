from pathlib import Path

import pytest

from sdd_context.minimax_agent import extract_python_source, run_minimax


class FakeResponse:
    headers = {"request-id": "req-test-1"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "model": "MiniMax-M2.1",
            "usage": {"input_tokens": 12, "output_tokens": 8},
            "content": [{"type": "text", "text": "```python\nVALUE = 2\n```"}],
        }


def test_run_minimax_applies_valid_code_and_records_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "test-only")
    monkeypatch.setattr("sdd_context.minimax_agent.httpx.post", lambda *args, **kwargs: FakeResponse())
    target = tmp_path / "catalog.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    record = run_minimax("change value", {"sources": {}}, tmp_path / "record.json", target)

    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert record["request_id"] == "req-test-1"
    assert record["applied_change"]["before_sha256"] != record["applied_change"]["after_sha256"]


def test_invalid_response_does_not_replace_target(tmp_path: Path) -> None:
    target = tmp_path / "catalog.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exactly one"):
        extract_python_source("Here is prose without a code block")
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
