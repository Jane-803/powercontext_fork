from __future__ import annotations

import argparse
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = Lock()
        self.data: dict[str, Any] = {"scopes": {}, "memories": {}}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def scope(self, key: str, title: str) -> str:
        with self.lock:
            scope_id = self.data["scopes"].get(key)
            if scope_id is None:
                safe = re.sub(r"[^a-zA-Z0-9-]", "-", key).strip("-")[:60]
                scope_id = f"scope-{safe}"
                self.data["scopes"][key] = scope_id
                self.data["memories"][scope_id] = []
                self.save()
            return scope_id

    def remember(self, scope_id: str, text: str) -> dict[str, str]:
        with self.lock:
            if scope_id not in self.data["memories"]:
                raise KeyError("unknown scope_id")
            record = {"artifact_id": f"memory-{len(self.data['memories'][scope_id]) + 1}", "text": text}
            self.data["memories"][scope_id].append(record)
            self.save()
            return record

    def prepare(self, scope_id: str, max_bytes: int) -> str | None:
        items = self.data["memories"].get(scope_id, [])
        if not items:
            return None
        content = "\n".join(item["text"] for item in items[-5:])
        return content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def make_handler(store: MemoryStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health/live":
                self.respond(HTTPStatus.OK, {"status": "ok", "implementation": "competition-mock"})
            else:
                self.respond(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            try:
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size))
                if self.path == "/v1/scopes":
                    scope_id = store.scope(body["idempotency_key"], body["title"])
                    self.respond(HTTPStatus.OK, {"scope_id": scope_id})
                elif self.path == "/v1/context/prepare":
                    content = store.prepare(body["scope_id"], int(body.get("max_bytes", 3000)))
                    self.respond(HTTPStatus.OK, {"status": "ready" if content else "empty", "content": content})
                elif self.path == "/v1/memory/remember":
                    record = store.remember(body["scope_id"], body["text"])
                    self.respond(HTTPStatus.OK, {"records": [record]})
                else:
                    self.respond(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def respond(self, status: HTTPStatus, body: dict[str, Any]) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local subset of the PowerContext HTTP contract for DSL rehearsal")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--data", type=Path, default=Path("records/mock-memory.json"))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(MemoryStore(args.data)))
    print(f"mock PowerContext listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
