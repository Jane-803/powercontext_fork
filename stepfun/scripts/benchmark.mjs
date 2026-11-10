// Run in the browser console after importing benchmark corpus and queries.
// Raw samples are intentionally emitted so medians can be audited.
export function summarize(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  return { samples, median: sorted[Math.floor(sorted.length / 2)], min: sorted[0], max: sorted.at(-1) };
}

export function retrievalMetrics(expected, actual, k = 5) {
  const top = actual.slice(0, k);
  const recall = expected.length ? expected.filter((id) => top.includes(id)).length / expected.length : 0;
  let dcg = 0;
  top.forEach((id, rank) => { if (expected.includes(id)) dcg += 1 / Math.log2(rank + 2); });
  const ideal = expected.slice(0, k).reduce((sum, _, rank) => sum + 1 / Math.log2(rank + 2), 0);
  return { [`recall@${k}`]: recall, [`ndcg@${k}`]: ideal ? dcg / ideal : 0 };
}
