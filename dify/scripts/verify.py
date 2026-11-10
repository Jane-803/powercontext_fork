from __future__ import annotations

import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

from mock_powercontext import MemoryStore, make_handler


ROOT = Path(__file__).resolve().parents[1]


def post(base_url: str, path: str, body: dict) -> dict:
    request = Request(
        base_url + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def main() -> None:
    dsl = yaml.safe_load((ROOT / "app.yml").read_text(encoding="utf-8"))
    nodes = {node["id"]: node["data"]["type"] for node in dsl["workflow"]["graph"]["nodes"]}
    required = {"start", "scope", "parse_scope", "recall", "parse_memory", "narrator", "remember", "finish"}
    assert required <= nodes.keys()
    assert nodes["narrator"] == "llm" and nodes["remember"] == "http-request"

    with tempfile.TemporaryDirectory() as temp:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(MemoryStore(Path(temp) / "memory.json")))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            scope = post(base_url, "/v1/scopes", {
                "title": "Timeline Grudge player comet-7",
                "summary": "validation",
                "idempotency_key": "timeline-grudge-comet-7",
            })["scope_id"]
            first = post(base_url, "/v1/context/prepare", {
                "scope_id": scope, "query": "old prank", "max_bytes": 3000,
            })
            assert first == {"status": "empty", "content": None}
            saved = post(base_url, "/v1/memory/remember", {
                "scope_id": scope,
                "kind": "decision",
                "text": "Player comet-7 visited the dinosaur era and gave every dinosaur an alarm clock.",
                "reason": "validation round one",
            })
            second = post(base_url, "/v1/context/prepare", {
                "scope_id": scope, "query": "dinosaur alarm clock", "max_bytes": 3000,
            })
            assert second["status"] == "ready" and "alarm clock" in second["content"]
            report = {
                "dsl_nodes": len(nodes),
                "first_round": first["status"],
                "memory_artifact": saved["records"][0]["artifact_id"],
                "second_round": second["status"],
                "recalled_text": second["content"],
                "status": "passed",
            }
            (ROOT / "records").mkdir(exist_ok=True)
            (ROOT / "records" / "validation.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            print(json.dumps(report, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
