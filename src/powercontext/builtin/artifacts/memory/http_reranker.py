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

"""HTTP score-based Memory reranking with global rank preservation."""

from __future__ import annotations

import math
from typing import Any

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision
from powercontext.builtin.inference import InferenceUsage


class HTTPMemoryReranker:
    """Score bounded candidate batches and select from the complete pool."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = "http-cross-encoder-v1",
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.endpoint = endpoint
        self.policy_id = policy_id
        self._client = client
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        if not candidates:
            raise ValueError("rerank requires at least one candidate")
        if limit < 1 or limit > len(candidates):
            raise ValueError("rerank limit must be between one and the candidate count")

        scores: dict[int, float] = {}
        requests = 0
        ranked = tuple(enumerate(candidates, start=1))
        for offset in range(0, len(ranked), self._batch_size):
            batch = ranked[offset : offset + self._batch_size]
            response = await self._client.post(
                self.endpoint,
                json={
                    "query": query,
                    "candidates": [{"rank": rank, "text": candidate.text} for rank, candidate in batch],
                },
            )
            requests += 1
            response.raise_for_status()
            expected = {rank for rank, _candidate in batch}
            scores.update(_validate_response(response, expected))

        selected = sorted(scores, key=lambda rank: (-scores[rank], rank))[:limit]
        return MemoryRerankDecision(
            selected_ranks=tuple(selected),
            usage=InferenceUsage(requests=requests),
        )


def _validate_response(response: httpx.Response, expected: set[int]) -> dict[int, float]:
    try:
        payload: Any = response.json()
    except (TypeError, ValueError) as error:
        raise ValueError("reranker response must be valid JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"scores"} or not isinstance(payload["scores"], list):
        raise ValueError("reranker response must contain only a scores list")

    result: dict[int, float] = {}
    for item in payload["scores"]:
        if not isinstance(item, dict) or set(item) != {"rank", "score"}:
            raise ValueError("each reranker score must contain only rank and score")
        rank = item["rank"]
        score = item["score"]
        if type(rank) is not int or rank not in expected or rank in result:
            raise ValueError("reranker scores must cover each batch rank exactly once")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("reranker scores must be finite numbers")
        result[rank] = float(score)
    if set(result) != expected:
        raise ValueError("reranker scores must cover each batch rank exactly once")
    return result


__all__ = ["HTTPMemoryReranker"]
