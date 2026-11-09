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

"""Portable full and incremental encodings for prepared context text."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"


class ContextPackError(ValueError):
    """Raised when a context pack or delta violates the wire contract."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _encoded(items: tuple[bytes, ...]) -> list[str]:
    return [base64.b64encode(item).decode("ascii") for item in items]


def _validate_items(items: object) -> tuple[bytes, ...]:
    if not isinstance(items, tuple) or any(not isinstance(item, bytes) for item in items):
        raise ContextPackError("items must be a tuple of bytes")
    for item in items:
        try:
            item.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ContextPackError("each context item must be valid UTF-8") from error
    return items


def _decode_items(values: object) -> tuple[bytes, ...]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ContextPackError("wire items must be a string array")
    decoded: list[bytes] = []
    try:
        for value in values:
            decoded.append(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError) as error:
        raise ContextPackError("wire items must use canonical Base64") from error
    return _validate_items(tuple(decoded))


def _digest(items: tuple[bytes, ...]) -> str:
    unsigned = {"schema": PACK_SCHEMA, "items": _encoded(items)}
    return "sha256:" + hashlib.sha256(_json_bytes(unsigned)).hexdigest()


def _valid_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value[7:], 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class ContextPack:
    items: tuple[bytes, ...]
    digest: str
    byte_count: int
    schema: str = field(default=PACK_SCHEMA, init=False)

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        checked = _validate_items(items)
        digest = _digest(checked)
        byte_count = 0
        while True:
            payload = {
                "schema": PACK_SCHEMA,
                "items": _encoded(checked),
                "digest": digest,
                "byte_count": byte_count,
            }
            measured = len(_json_bytes(payload))
            if measured == byte_count:
                return cls(items=checked, digest=digest, byte_count=byte_count)
            byte_count = measured

    @classmethod
    def from_content(cls, content: str, *, chunk_bytes: int = 512) -> ContextPack:
        if type(chunk_bytes) is not int or chunk_bytes <= 0:
            raise ContextPackError("chunk_bytes must be a positive integer")
        if not isinstance(content, str):
            raise ContextPackError("content must be text")
        items: list[bytes] = []
        chunk = bytearray()
        for character in content:
            encoded = character.encode("utf-8")
            if len(encoded) > chunk_bytes:
                raise ContextPackError("chunk limit cannot hold one UTF-8 code point")
            if chunk and len(chunk) + len(encoded) > chunk_bytes:
                items.append(bytes(chunk))
                chunk.clear()
            chunk.extend(encoded)
        if chunk:
            items.append(bytes(chunk))
        return cls.build(tuple(items))

    def to_bytes(self) -> bytes:
        payload = {
            "schema": self.schema,
            "items": _encoded(self.items),
            "digest": self.digest,
            "byte_count": self.byte_count,
        }
        encoded = _json_bytes(payload)
        if self.schema != PACK_SCHEMA or _digest(self.items) != self.digest or len(encoded) != self.byte_count:
            raise ContextPackError("context pack fields are inconsistent")
        return encoded

    @classmethod
    def from_bytes(cls, value: bytes) -> ContextPack:
        payload = _parse_object(value)
        if set(payload) != {"schema", "items", "digest", "byte_count"} or payload.get("schema") != PACK_SCHEMA:
            raise ContextPackError("invalid context pack fields")
        items = _decode_items(payload["items"])
        expected = cls.build(items)
        byte_count = payload["byte_count"]
        if type(byte_count) is not int or byte_count != expected.byte_count or payload["digest"] != expected.digest:
            raise ContextPackError("invalid context pack digest or byte count")
        return expected


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]
    schema: str = field(default=DELTA_SCHEMA, init=False)

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        prefix = 0
        for base_item, target_item in zip(base.items, target.items, strict=False):
            if base_item != target_item:
                break
            prefix += 1
        return cls(base.digest, target.digest, prefix, target.items[prefix:])

    def to_bytes(self) -> bytes:
        if (
            self.schema != DELTA_SCHEMA
            or not _valid_digest(self.base_digest)
            or not _valid_digest(self.target_digest)
            or type(self.prefix_items) is not int
            or self.prefix_items < 0
        ):
            raise ContextPackError("invalid context pack delta fields")
        _validate_items(self.appended)
        return _json_bytes(
            {
                "schema": self.schema,
                "base_digest": self.base_digest,
                "target_digest": self.target_digest,
                "prefix_items": self.prefix_items,
                "appended": _encoded(self.appended),
            }
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> ContextPackDelta:
        payload = _parse_object(value)
        expected_fields = {"schema", "base_digest", "target_digest", "prefix_items", "appended"}
        if set(payload) != expected_fields or payload.get("schema") != DELTA_SCHEMA:
            raise ContextPackError("invalid context pack delta fields")
        prefix = payload["prefix_items"]
        if type(prefix) is not int or prefix < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")
        if not _valid_digest(payload["base_digest"]) or not _valid_digest(payload["target_digest"]):
            raise ContextPackError("invalid context pack delta digest")
        return cls(
            base_digest=payload["base_digest"],
            target_digest=payload["target_digest"],
            prefix_items=prefix,
            appended=_decode_items(payload["appended"]),
        )


def _parse_object(value: bytes) -> dict[str, Any]:
    if not isinstance(value, bytes):
        raise ContextPackError("wire value must be bytes")
    try:
        payload = json.loads(value.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContextPackError("wire value must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ContextPackError("wire value must be a JSON object")
    return payload


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    if base.digest != delta.base_digest:
        raise ContextPackError("delta base digest does not match")
    if delta.prefix_items > len(base.items):
        raise ContextPackError("delta prefix exceeds the base item count")
    target = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if target.digest != delta.target_digest:
        raise ContextPackError("delta target digest does not match")
    return target


__all__ = [
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
