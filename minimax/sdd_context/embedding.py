from __future__ import annotations

import hashlib
import math
import re

DIMENSION = 96
TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+|\d+(?:\.\d+)?")


def embed(text: str) -> list[float]:
    """Create a deterministic local feature-hash vector without a model download."""
    vector = [0.0] * DIMENSION
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % DIMENSION
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector
