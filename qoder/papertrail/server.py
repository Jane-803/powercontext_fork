from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .service import PaperTrailService
from .store import PaperStore

MAX_BODY_BYTES = 64 * 1024


class RequestError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(SimpleHTTPRequestHandler):
    service: PaperTrailService

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/search":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            request = self.read_json_body()
        except RequestError as exc:
            self.respond(exc.status, {"error": exc.message})
            return
        try:
            payload = self.service.search(request)
        except ValueError as exc:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        else:
            self.respond(HTTPStatus.OK, payload)

    def read_json_body(self) -> dict:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise RequestError(HTTPStatus.LENGTH_REQUIRED, "Content-Length header is required")
        try:
            size = int(content_length)
        except ValueError as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, "Content-Length must be an integer") from exc
        if size <= 0:
            raise RequestError(HTTPStatus.BAD_REQUEST, "request body must not be empty")
        if size > MAX_BODY_BYTES:
            raise RequestError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"request body must not exceed {MAX_BODY_BYTES} bytes"
            )
        raw = self.rfile.read(size)
        try:
            body = json.loads(raw)
        except UnicodeDecodeError as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, "request body must be UTF-8 encoded JSON") from exc
        except json.JSONDecodeError as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, f"request body is not valid JSON: {exc.msg}") from exc
        if not isinstance(body, dict):
            raise RequestError(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
        return body

    def respond(self, status: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data", type=Path, default=Path("data/sample-papers.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    store = PaperStore(root / ".runtime" / "seekdb")
    service = PaperTrailService(store)
    imported = service.import_file(root / args.data)
    Handler.service = service
    Handler.directory = str(root / "site")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), lambda *a, **kw: Handler(*a, directory=Handler.directory, **kw))
    print(f"PaperTrail ready: http://127.0.0.1:{args.port} ({imported} papers imported)")
    server.serve_forever()


if __name__ == "__main__":
    main()
