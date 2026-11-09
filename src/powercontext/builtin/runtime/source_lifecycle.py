"""Persistent Source dependency lifecycle propagation."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import insert, select, update

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_NODES_TABLE
from powercontext.builtin.sources import validate_scope_id
from powercontext.sources import SourceRef


class SourceLifecycleError(ValueError):
    """A lifecycle graph, event, or resolution request is invalid."""


class SourceLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    node_id: str
    revision: int = Field(gt=0)
    sequence: int = Field(gt=0)
    available: bool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class SourceLifecycleApplication:
    def __init__(self, runtime, database: AsyncDatabase) -> None:
        self._runtime = runtime
        self._database = database

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self._runtime, self._database, validate_scope_id(scope_id))

    async def filter_topic_result(self, scope_id: str, result):
        async with self._database.transaction() as connection:
            rows = (
                await connection.execute(
                    select(SOURCE_LIFECYCLE_NODES_TABLE.c.reference).where(
                        SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
                        SOURCE_LIFECYCLE_NODES_TABLE.c.kind == "topic",
                        SOURCE_LIFECYCLE_NODES_TABLE.c.available.is_(False),
                    )
                )
            ).scalars()
            unavailable = {
                (ref.family, ref.artifact_id, ref.revision)
                for value in rows
                for ref in (ArtifactRef.model_validate(json.loads(bytes(value))),)
            }
        if not unavailable:
            return result
        return result.model_copy(
            update={
                "hits": tuple(
                    hit
                    for hit in result.hits
                    if (hit.artifact_ref.family, hit.artifact_ref.artifact_id, hit.artifact_ref.revision)
                    not in unavailable
                )
            }
        )


class ScopedSourceLifecycle:
    def __init__(self, runtime, database: AsyncDatabase, scope_id: str) -> None:
        self._runtime = runtime
        self._database = database
        self.scope_id = scope_id

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int) -> None:
        if type(revision) is not int or revision < 1:
            raise SourceLifecycleError("revision must be a positive integer")
        await self._runtime.records.for_scope(self.scope_id).get_source(source_ref.source_type, source_ref.source_id)
        await self._register(node_id, "source", source_ref.model_dump(mode="json"), (), None, revision, True)

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        await self._runtime.memory.for_scope(self.scope_id).get_from_lifecycle(citation)
        await self._register(node_id, "memory", citation.model_dump(mode="json"), parents, policy, None, None)

    async def register_topic(
        self,
        node_id: str,
        artifact_ref: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        if artifact_ref.family != "topic-memory":
            raise SourceLifecycleError("topic reference must use the topic-memory family")
        await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
            artifact_ref.family, artifact_ref.artifact_id, artifact_ref.revision
        )
        await self._register(node_id, "topic", artifact_ref.model_dump(mode="json"), parents, policy, None, None)

    async def _register(self, node_id, kind, reference, parents, policy, revision, available) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node_id must not be empty")
        if kind != "source":
            if not parents or len(set(parents)) != len(parents) or node_id in parents:
                raise SourceLifecycleError("derived nodes require unique, previously registered parents")
            if policy not in {"all", "any"}:
                raise SourceLifecycleError("policy must be all or any")
        encoded_ref = json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()
        encoded_parents = json.dumps(parents, separators=(",", ":")).encode()
        async with self._database.transaction() as connection:
            existing = (
                await connection.execute(
                    select(SOURCE_LIFECYCLE_NODES_TABLE).where(
                        SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id,
                        SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                    )
                )
            ).mappings().one_or_none()
            identity = (kind, encoded_ref, encoded_parents, policy, revision)
            if existing is not None:
                stored = (
                    existing["kind"], existing["reference"], existing["parents"], existing["policy"], existing["revision"]
                )
                if stored != identity:
                    raise SourceLifecycleError("node_id is already bound differently")
                return
            parent_rows = ()
            if parents:
                parent_rows = (
                    await connection.execute(
                        select(SOURCE_LIFECYCLE_NODES_TABLE.c.node_id, SOURCE_LIFECYCLE_NODES_TABLE.c.available).where(
                            SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id,
                            SOURCE_LIFECYCLE_NODES_TABLE.c.node_id.in_(parents),
                        )
                    )
                ).all()
                if {row[0] for row in parent_rows} != set(parents):
                    raise SourceLifecycleError("parent is not registered")
                states = [bool(row[1]) for row in parent_rows]
                available = all(states) if policy == "all" else any(states)
            await connection.execute(
                insert(SOURCE_LIFECYCLE_NODES_TABLE).values(
                    scope_id=self.scope_id,
                    node_id=node_id,
                    kind=kind,
                    reference=encoded_ref,
                    parents=encoded_parents,
                    policy=policy,
                    revision=revision,
                    available=available,
                    sequence=0,
                )
            )
        if kind == "memory" and not available:
            await self._runtime.memory.for_scope(self.scope_id).set_lifecycle_state(
                MemoryCitation.model_validate(reference), False
            )

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        async with self._database.transaction() as connection:
            rows = (
                await connection.execute(
                    select(SOURCE_LIFECYCLE_NODES_TABLE)
                    .where(SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id)
                    .order_by(SOURCE_LIFECYCLE_NODES_TABLE.c.node_id)
                )
            ).mappings().all()
        by_id = {str(row["node_id"]): row for row in rows}
        root = by_id.get(event.node_id)
        if root is None or root["kind"] != "source" or root["revision"] != event.revision:
            raise SourceLifecycleError("unknown Source or lifecycle revision mismatch")
        payload = event.model_dump_json().encode()
        sequence = int(root["sequence"])
        if event.sequence < sequence or (event.sequence == sequence and root["event_payload"] != payload):
            raise SourceLifecycleError("event sequence is stale or conflicts")
        if event.sequence == sequence:
            return sorted(node for node, row in by_id.items() if row["available"])
        states = {
            node: (event.available if node == event.node_id else bool(row["available"]))
            for node, row in by_id.items()
            if row["kind"] == "source"
        }
        pending = {node for node, row in by_id.items() if row["kind"] != "source"}
        while pending:
            progressed = False
            for node in tuple(pending):
                row = by_id[node]
                parents = json.loads(bytes(row["parents"]))
                if not all(parent in states for parent in parents):
                    continue
                support = [states[parent] for parent in parents]
                states[node] = all(support) if row["policy"] == "all" else any(support)
                pending.remove(node)
                progressed = True
            if not progressed:
                raise SourceLifecycleError("lifecycle graph contains a cycle")
        for node, row in by_id.items():
            if row["kind"] == "memory" and states[node] != bool(row["available"]):
                await self._runtime.memory.for_scope(self.scope_id).set_lifecycle_state(
                    MemoryCitation.model_validate(json.loads(bytes(row["reference"]))), states[node]
                )
        async with self._database.transaction() as connection:
            for node, available in states.items():
                values = {"available": available}
                if node == event.node_id:
                    values.update(sequence=event.sequence, event_payload=payload)
                await connection.execute(
                    update(SOURCE_LIFECYCLE_NODES_TABLE)
                    .where(
                        SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id,
                        SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node,
                    )
                    .values(**values)
                )
        return sorted(node for node, available in states.items() if available)

    async def resolve(self, node_id: str, *, purpose: Literal["generation", "audit"]):
        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("unknown resolution purpose")
        async with self._database.transaction() as connection:
            row = (
                await connection.execute(
                    select(SOURCE_LIFECYCLE_NODES_TABLE).where(
                        SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id,
                        SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                    )
                )
            ).mappings().one_or_none()
        if row is None or (purpose == "generation" and not row["available"]):
            raise SourceLifecycleError("node is unavailable or unknown")
        value = json.loads(bytes(row["reference"]))
        return {
            "source": SourceRef,
            "memory": MemoryCitation,
            "topic": ArtifactRef,
        }[row["kind"]].model_validate(value)


__all__ = ["SourceLifecycleError", "SourceLifecycleEvent"]
