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

"""Concurrent request coalescing and bounded caching for embeddings."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass(frozen=True, slots=True)
class _ComputedVector:
    vector: EmbeddingVector
    batch_id: int
    usage: InferenceUsage


class CoalescingEmbeddingModel:
    """Share in-flight text embeddings and cache successful vectors."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if type(max_batch_size) is not int or max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, (int, float)) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be non-negative")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be non-negative")
        self.profile = model.profile
        self._model = model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = float(coalesce_ms) / 1000
        self._cache_size = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[_ComputedVector]] = {}
        self._pending: deque[str] = deque()
        self._dispatcher: asyncio.Task[None] | None = None
        self._next_batch_id = 0

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        resolved: dict[str, EmbeddingVector] = {}
        waiting: dict[str, asyncio.Future[_ComputedVector]] = {}
        for text in dict.fromkeys(texts):
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                resolved[text] = cached
                continue
            future = self._inflight.get(text)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[text] = future
                self._pending.append(text)
            waiting[text] = future

        if self._pending and (self._dispatcher is None or self._dispatcher.done()):
            self._dispatcher = asyncio.create_task(self._dispatch())

        usages: dict[int, InferenceUsage] = {}
        for text, future in waiting.items():
            computed = await asyncio.shield(future)
            resolved[text] = computed.vector
            usages[computed.batch_id] = computed.usage

        return EmbeddingResult(
            vectors=tuple(resolved[text] for text in texts),
            usage=_sum_usage(tuple(usages.values())),
        )

    async def _dispatch(self) -> None:
        await asyncio.sleep(self._coalesce_seconds)
        while self._pending:
            texts = tuple(self._pending.popleft() for _ in range(min(len(self._pending), self._max_batch_size)))
            self._next_batch_id += 1
            batch_id = self._next_batch_id
            try:
                result = await self._model.embed(texts)
                if len(result.vectors) != len(texts):
                    raise ValueError("embedding provider returned an unexpected vector count")
            except BaseException as error:
                for text in texts:
                    future = self._inflight.pop(text, None)
                    if future is not None and not future.done():
                        future.set_exception(error)
                continue

            for text, vector in zip(texts, result.vectors, strict=True):
                if self._cache_size:
                    self._cache[text] = vector
                    self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                future = self._inflight.pop(text, None)
                if future is not None and not future.done():
                    future.set_result(_ComputedVector(vector=vector, batch_id=batch_id, usage=result.usage))


def _sum_usage(values: tuple[InferenceUsage, ...]) -> InferenceUsage:
    def total(field: str) -> int | None:
        observed = [getattr(value, field) for value in values]
        return sum(value or 0 for value in observed) if any(value is not None for value in observed) else None

    return InferenceUsage(
        requests=sum(value.requests for value in values),
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
    )


__all__ = ["CoalescingEmbeddingModel"]
