import math

from papertrail.embedding import DIMENSION, embed


def test_embedding_is_deterministic_and_normalized():
    first = embed("retrieval augmented generation")
    assert first == embed("retrieval augmented generation")
    assert len(first) == DIMENSION
    assert math.isclose(sum(value * value for value in first), 1.0)
