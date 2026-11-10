from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx


class PowerContextState:
    """Persist and restore task progress through the PowerContext 1.2 HTTP contract."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8000")).rstrip("/")
        token = os.getenv("POWERCONTEXT_API_TOKEN")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        request_headers = {**self.headers, **kwargs.pop("headers", {})}
        response = httpx.request(method, self.base_url + path, headers=request_headers, timeout=30, **kwargs)
        if response.is_error:
            raise RuntimeError(f"PowerContext {method} {path} returned {response.status_code}: {response.text}")
        return response

    def ensure_scope(self) -> str:
        payload = {
            "title": "MiniMax SDD context validation",
            "summary": "Filter nearby places by minimum rating without changing existing behavior",
            "idempotency_key": os.getenv("POWERCONTEXT_SCOPE_KEY", "minimax-sdd-filter-v1"),
        }
        return self._request("POST", "/v1/scopes", json=payload).json()["scope_id"]

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        scope_id = self.ensure_scope()
        scope_path = f"/v1/scopes/{quote(scope_id, safe='')}"
        source = self._request(
            "POST", scope_path + "/sources", json={"source_type": "content", "content": state}
        ).json()
        citation = {"kind": "source", "source_ref": {"name": "content", "source_id": source["source_id"]}}
        content = {
            "schema": "powercontext.handoff.v1",
            "objective": state["objective"],
            "state": [{"text": item, "citations": [citation]} for item in state.get("completed", [])],
            "disposition": "continuable" if state.get("disposition", "partial") == "partial" else state["disposition"],
            "next_action": (
                {"text": state["next_action"], "citations": [citation]} if state.get("next_action") else None
            ),
            "omissions": [{"text": item, "citation": None} for item in state.get("todo", [])],
        }
        listing = self._request("GET", scope_path + "/artifacts/handoff").json()["items"]
        if not listing:
            result = self._request(
                "POST", scope_path + "/artifacts", json={"family": "handoff", "content": content}
            )
        else:
            artifact_id = listing[0]["artifact_id"]
            artifact_path = scope_path + f"/artifacts/handoff/{quote(artifact_id, safe='')}"
            current = self._request("GET", artifact_path)
            result = self._request(
                "PUT", artifact_path, headers={**self.headers, "If-Match": current.headers["ETag"]}, json={"content": content}
            )
        payload = result.json()
        return {"scope_id": scope_id, "artifact_id": payload["artifact_id"], "revision": payload["revision"]}

    def load(self) -> dict[str, Any] | None:
        scope_id = self.ensure_scope()
        scope_path = f"/v1/scopes/{quote(scope_id, safe='')}"
        items = self._request("GET", scope_path + "/artifacts/handoff").json()["items"]
        if not items:
            return None
        artifact_id = items[0]["artifact_id"]
        result = self._request(
            "GET", scope_path + f"/artifacts/handoff/{quote(artifact_id, safe='')}"
        ).json()
        return {"scope_id": scope_id, "artifact_id": artifact_id, "revision": result["revision"], **result["content"]}
