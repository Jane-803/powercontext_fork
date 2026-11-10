# ADR: preserve source order while filtering

The caller already ranks nearby places. `filter_places` is a predicate-only operation and must not sort its input.
New filters must therefore be combined in the existing list comprehension and must retain the original order.
