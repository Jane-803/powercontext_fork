from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .service import PaperTrailService
from .store import PaperStore


class Handler(SimpleHTTPRequestHandler):
    service: PaperTrailService

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/search":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(size))
            self.respond(HTTPStatus.OK, self.service.search(request))
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

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
