# Place filtering contract v1

Status: current

`filter_places` accepts optional `category` and `max_distance_m` filters. Results retain input order.
Negative `max_distance_m` values raise `ValueError`. Calling without filters returns every place.
