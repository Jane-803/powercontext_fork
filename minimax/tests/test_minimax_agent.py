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
    monkeypatch.setenv("MINIMAX_API_FORMAT", "anthropic")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.test/anthropic")
    monkeypatch.setattr("sdd_context.minimax_agent.httpx.post", lambda *args, **kwargs: FakeResponse())
    target = tmp_path / "catalog.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    record = run_minimax("change value", {"sources": {}}, tmp_path / "record.json", target)

    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert record["request_id"] == "req-test-1"
    assert record["applied_change"]["before_sha256"] != record["applied_change"]["after_sha256"]


def test_openai_compatible_response_is_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class OpenAIResponse(FakeResponse):
        headers = {}

        def json(self) -> dict:
            return {
                "model": "MiniMax-M2.5",
                "request_id": "req-openai-1",
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                "choices": [{"message": {"content": "```python\nVALUE = 3\n```"}}],
            }

    monkeypatch.setenv("MINIMAX_API_KEY", "test-only")
    monkeypatch.setenv("MINIMAX_API_FORMAT", "openai")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr("sdd_context.minimax_agent.httpx.post", lambda *args, **kwargs: OpenAIResponse())
    target = tmp_path / "catalog.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    record = run_minimax("change value", {"sources": {}}, tmp_path / "record.json", target)

    assert target.read_text(encoding="utf-8") == "VALUE = 3\n"
    assert record["provider"] == "MiniMax openai-compatible API"
    assert record["request_id"] == "req-openai-1"


def test_run_minimax_can_create_a_new_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "test-only")
    monkeypatch.setenv("MINIMAX_API_FORMAT", "anthropic")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.test/anthropic")
    monkeypatch.setattr("sdd_context.minimax_agent.httpx.post", lambda *args, **kwargs: FakeResponse())
    target = tmp_path / "generated" / "catalog.py"

    record = run_minimax("create module", {"sources": {}}, tmp_path / "record.json", target)

    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert record["applied_change"]["before_sha256"] != record["applied_change"]["after_sha256"]


def test_invalid_response_does_not_replace_target(tmp_path: Path) -> None:
    target = tmp_path / "catalog.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exactly one"):
        extract_python_source("Here is prose without a code block")
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
