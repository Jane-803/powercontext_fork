from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def run_minimax(task: str, context: dict[str, Any], output: Path) -> dict[str, Any]:
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("Set MINIMAX_API_KEY; credentials are never written to the record.")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.1")
    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic").rstrip("/")
    prompt = (
        "You are modifying the supplied Python business module. Use only the current specifications, preserve the "
        "listed compatibility behavior, and return the complete replacement content of sample_app/catalog.py inside "
        "one Python fenced code block. Do not modify tests.\n\n"
        f"TASK:\n{task}\n\nENGINEERING CONTEXT:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )
    request_body = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    response = httpx.post(
        base_url + "/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json=request_body,
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    text = "\n".join(block["text"] for block in body.get("content", []) if block.get("type") == "text")
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "MiniMax Anthropic-compatible API",
        "base_url": base_url,
        "model": body.get("model", model),
        "task": task,
        "context_sha256": hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest(),
        "request_id": response.headers.get("request-id") or response.headers.get("x-request-id"),
        "usage": body.get("usage"),
        "response": text,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as record_file:
        record_file.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record
