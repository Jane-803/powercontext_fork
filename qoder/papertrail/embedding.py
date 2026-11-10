from __future__ import annotations

import hashlib
import math
import re

DIMENSION = 128
TOKENS = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+|\d+(?:\.\d+)?")


def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSION
    for token in TOKENS.findall(text.lower()):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % DIMENSION
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector
