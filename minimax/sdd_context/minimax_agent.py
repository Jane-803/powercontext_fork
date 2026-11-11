from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def extract_python_source(response: str) -> str:
    blocks = re.findall(r"```python\s*\n(.*?)```", response, flags=re.DOTALL | re.IGNORECASE)
    if len(blocks) != 1:
        raise RuntimeError("MiniMax must return exactly one fenced Python code block; target was not changed.")
    source = blocks[0].strip() + "\n"
    compile(source, "<minimax-response>", "exec")
    return source


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_minimax(task: str, context: dict[str, Any], output: Path, target: Path | None = None) -> dict[str, Any]:
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("Set MINIMAX_API_KEY; credentials are never written to the record.")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M3.1-Flash")
    api_format = os.getenv("MINIMAX_API_FORMAT", "openai").lower()
    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1").rstrip("/")
    prompt = (
        "You are modifying the supplied Python business module. Use only the current specifications, preserve the "
        "listed compatibility behavior, and return the complete replacement content of sample_app/catalog.py inside "
        "one Python fenced code block. Do not modify tests.\n\n"
        f"TASK:\n{task}\n\nENGINEERING CONTEXT:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )
    request_body = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    if api_format == "openai":
        url = base_url + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    elif api_format == "anthropic":
        url = base_url + "/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        raise RuntimeError("MINIMAX_API_FORMAT must be 'openai' or 'anthropic'.")
    response = httpx.post(url, headers=headers, json=request_body, timeout=120)
    response.raise_for_status()
    body = response.json()
    if api_format == "openai":
        choices = body.get("choices") or []
        text = choices[0].get("message", {}).get("content", "") if choices else ""
    else:
        text = "\n".join(block["text"] for block in body.get("content", []) if block.get("type") == "text")
    before = target.read_bytes() if target is not None else None
    generated = extract_python_source(text) if target is not None else None
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provider": f"MiniMax {api_format}-compatible API",
        "base_url": base_url,
        "model": body.get("model", model),
        "task": task,
        "context_sha256": hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest(),
        "request_id": (
            response.headers.get("request-id")
            or response.headers.get("x-request-id")
            or body.get("request_id")
            or body.get("id")
        ),
        "usage": body.get("usage"),
        "response": text,
    }
    if target is not None and before is not None and generated is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        generated_bytes = generated.encode("utf-8")
        with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as temporary:
            temporary.write(generated_bytes)
            temporary_path = Path(temporary.name)
        temporary_path.replace(target)
        record["applied_change"] = {
            "target": f"{target.parent.name}/{target.name}",
            "before_sha256": _sha256(before),
            "after_sha256": _sha256(generated_bytes),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as record_file:
        record_file.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record
