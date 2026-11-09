# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pi v3 session branch parsing and durable event capture."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.connectors import (
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
)
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TextEvidence


class PiSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


class PiEventSource(Source):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    try:
        text = value.content.decode("utf-8-sig", errors="strict")
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Pi session JSONL") from error
    if not records or not isinstance(records[0], dict):
        raise ValueError("Pi session header is required")
    header = records[0]
    session_id = header.get("id")
    if header.get("type") != "session" or header.get("version") != 3 or not isinstance(session_id, str) or not session_id:
        raise ValueError("invalid Pi v3 session header")

    by_id: dict[str, dict[str, Any]] = {}
    last_id: str | None = None
    for raw in records[1:]:
        if not isinstance(raw, dict):
            raise ValueError("Pi event must be an object")
        event_id = raw.get("id")
        parent_id = raw.get("parentId")
        if not isinstance(event_id, str) or not event_id or event_id in by_id:
            raise ValueError("Pi event IDs must be unique non-empty strings")
        if parent_id is not None and (not isinstance(parent_id, str) or parent_id not in by_id):
            raise ValueError("Pi event parent must reference an earlier event")
        by_id[event_id] = raw
        last_id = event_id

    leaf_id = value.leaf_id if value.leaf_id is not None else last_id
    if leaf_id is None:
        return ()
    if leaf_id not in by_id:
        raise ValueError("selected Pi leaf does not exist")
    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: str | None = leaf_id
    while current is not None:
        if current in seen:
            raise ValueError("Pi session graph contains a cycle")
        seen.add(current)
        record = by_id[current]
        path.append(record)
        current = record.get("parentId")
    path.reverse()

    events = []
    for record in path:
        event = _visible_event(session_id, record)
        if event is not None:
            events.append(event)
    return tuple(events)


def _visible_event(session_id: str, record: dict[str, Any]) -> PiEventInput | None:
    event_type = record.get("type")
    if not isinstance(event_type, str):
        raise ValueError("Pi event type must be a string")
    role: str
    body: str
    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("role"), str):
            return None
        role = message["role"]
        if role == "toolResult":
            visible = _visible_parts(message.get("content"))
            name, call_id = message.get("toolName"), message.get("toolCallId")
            if not isinstance(name, str) or not isinstance(call_id, str) or not visible:
                return None
            body = f"[tool_result {name} {call_id}] {visible}"
        elif role == "bashExecution":
            command, output = message.get("command"), message.get("output")
            if not isinstance(command, str):
                return None
            body = f"$ {command}" + (f"\n{output}" if isinstance(output, str) and output else "")
        else:
            body = _visible_parts(message.get("content"))
            if not body:
                return None
    elif event_type in {"compaction", "branch_summary"}:
        summary = record.get("summary")
        if not isinstance(summary, str) or not summary:
            return None
        role = event_type
        body = summary
    elif event_type == "custom_message":
        body = _visible_parts(record.get("content"))
        if not body:
            return None
        role = "custom"
    else:
        return None
    return PiEventInput(
        session_id=session_id,
        event_id=record["id"],
        parent_id=record.get("parentId"),
        event_type=event_type,
        role=role,
        content=f"{role}: {body}",
        record=record,
    )


def _visible_parts(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
            parts.append(part["text"])
        elif isinstance(part, dict) and part.get("type") == "toolCall":
            name, call_id = part.get("name"), part.get("id")
            if isinstance(name, str) and isinstance(call_id, str):
                arguments = json.dumps(part.get("arguments"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                parts.append(f"[tool_call {name} {call_id}] {arguments}")
    return "\n".join(parts)


def _source_id(session_id: str, event_id: str) -> str:
    source_id = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"Pi event source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return source_id


@dataclass(frozen=True, slots=True)
class _PiEventProjection:
    name: str = "powercontext.text-evidence"
    version: str = "1"
    source_class: type[PiEventSource] = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pi-event",
            source_id=source.source_id,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


@dataclass(frozen=True, slots=True)
class _PiEventSourceDefinition:
    name: str = "pi-event"
    version: str = "1"
    input_class: type[PiEventInput] = PiEventInput
    source_class: type[PiEventSource] = PiEventSource
    projections: tuple[_PiEventProjection, ...] = (_PiEventProjection(),)

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = _source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            source_id=source_id,
            definition_version=self.version,
            materialization=SourceMaterialization.CAPTURED,
            **value.model_dump(),
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput.model_validate(
            source.model_dump(exclude={"name", "source_id", "definition_version", "materialization", "description"})
        )


PI_EVENT_SOURCE_DEFINITION = _PiEventSourceDefinition()


class PiSessionConnector:
    name = "pi-session-history"
    version = "1"
    source_definitions = frozenset({"pi-event"})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        events = parse_pi_session(PiSessionInput(content=self._path.read_bytes(), leaf_id=self._leaf_id))
        imported = _checkpoint_events(session.checkpoint)
        updated = dict(imported)
        for event in events:
            identity = _source_id(event.session_id, event.event_id)
            fingerprint = _fingerprint(event)
            previous = imported.get(identity)
            if previous is not None:
                if previous != fingerprint:
                    raise ValueError(f"previously imported Pi event {event.event_id!r} was modified")
                continue
            await session.submit(identity, "pi-event", event)
            updated[identity] = fingerprint
        return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint={"events": updated})


def _checkpoint_events(checkpoint: object) -> dict[str, str]:
    if checkpoint is None:
        return {}
    if not isinstance(checkpoint, dict) or set(checkpoint) != {"events"} or not isinstance(checkpoint["events"], dict):
        raise ValueError("invalid Pi session checkpoint")
    events = checkpoint["events"]
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in events.items()):
        raise ValueError("invalid Pi session checkpoint entries")
    return dict(events)


def _fingerprint(event: PiEventInput) -> str:
    encoded = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PI_EVENT_SOURCE_DEFINITION",
    "PiEventInput",
    "PiEventSource",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
]
