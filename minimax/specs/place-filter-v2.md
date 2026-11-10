# Place filtering contract v2

Status: current; supersedes v1

`filter_places` additionally accepts optional `min_rating`. A place matches when its rating is greater than or equal
to the threshold. Thresholds below 0 or above 5 raise `ValueError`.

Compatibility requirements remain authoritative: category and maximum-distance filtering keep their existing
inclusive behavior, negative maximum distance remains invalid, omitted `min_rating` changes nothing, and result
order remains the caller's input order.
