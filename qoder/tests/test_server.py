import json
import socket
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from papertrail.server import MAX_BODY_BYTES, Handler


class StubService:
    def search(self, request):
        query = request["query"]
        if query == "invalid":
            raise ValueError("query must not be empty")
        if query == "internal":
            raise RuntimeError("database unavailable")
        return {"query": query, "result_count": 0, "results": []}


class QuietHandler(Handler):
    service = StubService()

    def log_message(self, format, *args):
        return


@pytest.fixture()
def port():
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post(port, body=None, headers=None, path="/api/search"):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("POST", path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", "replace")}
        return response.status, payload
    finally:
        connection.close()


def test_search_endpoint_returns_json_result(port):
    status, payload = post(port, json.dumps({"query": "retrieval"}).encode())
    assert status == HTTPStatus.OK
    assert payload == {"query": "retrieval", "result_count": 0, "results": []}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"", "must not be empty"),
        (b"{", "not valid JSON"),
        (b"[]", "must be a JSON object"),
        (b"\xff", "UTF-8"),
    ],
)
def test_search_endpoint_rejects_malformed_bodies(port, body, message):
    status, payload = post(port, body)
    assert status == HTTPStatus.BAD_REQUEST
    assert message in payload["error"]


def test_search_endpoint_rejects_invalid_content_length(port):
    status, payload = post(port, b"{}", headers={"Content-Length": "abc"})
    assert status == HTTPStatus.BAD_REQUEST
    assert "Content-Length" in payload["error"]


def test_search_endpoint_rejects_oversized_body(port):
    status, payload = post(port, b"{}", headers={"Content-Length": str(MAX_BODY_BYTES + 1)})
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert "exceed" in payload["error"]


def test_search_endpoint_requires_content_length(port):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(b"POST /api/search HTTP/1.0\r\nHost: localhost\r\n\r\n")
        chunks = []
        while chunk := connection.recv(4096):
            chunks.append(chunk)
    response = b"".join(chunks).decode("utf-8", "replace")
    assert "411" in response.splitlines()[0]
    assert "Content-Length header is required" in response


def test_search_endpoint_maps_value_error_to_bad_request(port):
    status, payload = post(port, json.dumps({"query": "invalid"}).encode())
    assert status == HTTPStatus.BAD_REQUEST
    assert payload["error"] == "query must not be empty"


def test_search_endpoint_maps_unexpected_error_to_internal_error(port):
    status, payload = post(port, json.dumps({"query": "internal"}).encode())
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert payload["error"] == "database unavailable"


def test_unknown_post_path_returns_not_found(port):
    status, _ = post(port, b"{}", path="/api/other")
    assert status == HTTPStatus.NOT_FOUND
