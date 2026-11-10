---
name: amap-nearby-explorer
description: Use AMap place search and walking directions to recommend nearby places from a supplied origin when the user asks where to go, eat, drink, shop, relax, or visit within walking distance.
---

# AMap Nearby Explorer

Recommend real nearby places that satisfy the user's stated constraints, and verify how to walk to every recommendation. Treat AMap responses as the only source of place and route facts.

## Understand the request

Extract before calling tools:

- the supplied origin coordinate and city;
- requested place category or keywords;
- hard constraints such as maximum walking time, distance, price, or required features;
- requested result count, defaulting to 3 when omitted and always capped at 3;
- ranking preferences such as nearest first.

Use the provided origin coordinate exactly in AMap's `longitude,latitude` order. Do not geocode a named origin when an evaluation coordinate is supplied. If a necessary hard constraint is genuinely ambiguous, make the narrowest reasonable interpretation and state it briefly; do not invent a user location.

## Find candidates with AMap

1. Call the AMap MCP place-around tool `maps_around_search` using the exact origin, the supplied city where supported, and category-specific keywords. Do not replace a specific request such as “咖啡馆” with a generic attraction search.
2. Retrieve more candidates than the requested count so route validation can discard unsuitable results. For a walking-time limit, use a generously derived search radius only to gather candidates; straight-line/search distance is never proof that the walking limit is met. Prefer up to roughly 10–20 nearby candidates and paginate or modestly widen the radius once when too few plausible candidates are returned.
3. Keep only POIs whose returned type/name/category is compatible with the request. Remove duplicates by POI ID, or by normalized name plus address/location when no ID exists. Preserve the exact AMap name, address and destination coordinate.
4. Do not present sponsored-looking order, search rank, straight-line distance, ratings, price, opening status, quietness, queues, popularity, or quality as facts unless those fields are actually present in the tool response and directly support the statement.

If nearby search fails because of a transient tool/service error, retry once with the same intent. Do not silently switch cities or fabricate candidates.

## Verify walking routes

For plausible candidates, call the AMap MCP walking-directions tool `maps_direction_walking` independently from the same exact origin to each POI's returned coordinate.

- Read walking distance and duration from the route result. Compare the original duration in seconds against a time limit before formatting it. Convert meters to user-friendly meters/kilometers and seconds to approximate minutes without changing the underlying value; round minutes conservatively so a borderline route is not made to appear within a hard limit.
- When AMap returns multiple valid walking paths, use the shortest-duration valid path and keep its matching distance. Never combine time from one path with distance from another.
- A search radius or POI straight-line distance must not substitute for walking directions.
- If walking directions fail or contain no valid path, do not include that POI as a verified recommendation. Continue validating other candidates. A single route may be retried once after checking coordinate order and parameters.
- Apply every hard constraint after route validation. In particular, exclude any route whose returned duration exceeds the user's maximum, even if it is otherwise attractive.

Continue through candidates until the requested number of valid recommendations is found or the reasonable candidate pool is exhausted. Do not turn independent alternatives into a multi-stop route.

## Rank and explain

Filter first, then rank. Explicit user preferences control ranking:

- for “优先近一点/最快到达”, sort by verified walking duration, breaking ties with walking distance;
- for another supported preference, use only corresponding AMap fields, then walking duration as a tie-breaker;
- without a ranking preference, favor category relevance and then shorter verified walking duration.

Give a short reason grounded in returned facts, such as closer walking time, matching POI type, or a returned facility/feature. Never infer subjective qualities such as “安静”“不排队”“适合办公” from a name or category. If the user asked for such a property but AMap did not verify it, say `未核实` rather than claiming it. If an unverified property is stated as mandatory, explain that it cannot be confirmed and do not present a place as satisfying that condition.

## Answer

Be concise and return at most the requested count and never more than 3. Use a numbered list or compact table containing, for every recommendation:

- place name;
- address;
- verified walking distance;
- verified walking time;
- one evidence-based recommendation reason.

State that walking figures come from AMap route planning. Keep names, addresses, distances, durations, and ordering consistent with the tool results.

If fewer places qualify, return only verified qualifying places and briefly say that the search/route results did not yield enough places within the constraints. If none qualify, say so and optionally suggest one concrete relaxation, such as a longer walking-time limit or broader category. If place search or routing remains unavailable after one retry, identify the failed stage and do not output invented recommendations. Mark missing addresses or requested-but-unverified attributes explicitly as `未提供` or `未核实`.
