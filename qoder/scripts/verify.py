from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.service import PaperTrailService


class EvidenceStore:
    """A recording double for deterministic preflight; Linux E2E uses real seekdb."""

    def __init__(self):
        self.papers = []
        self.query_record = None

    def upsert(self, papers):
        self.papers = papers
        return len(papers)

    def search(self, query, limit, year_from):
        self.query_record = {"method": "Collection.query", "query": query, "limit": limit, "year_from": year_from}
        return [
            {"id": "p4", "title": "Lost in the Middle", "authors": "Liu et al.", "year": 2023, "abstract": "long context retrieval", "source": "https://arxiv.org/abs/2307.03172", "tags": "long context", "score": 0.91}
        ]


root = ROOT
store = EvidenceStore()
service = PaperTrailService(store)
count = service.import_file(root / "data" / "sample-papers.json")
result = service.search({"query": "long context retrieval quality", "year_from": 2020, "limit": 3})
record = {"imported": count, "request": {"query": "long context retrieval quality", "year_from": 2020}, "database_call_shape": store.query_record, "response": result, "preflight_note": "Run python -m papertrail.server for real seekdb execution."}
with (root / "records" / "validation-preflight.json").open("w", encoding="utf-8", newline="\n") as output:
    json.dump(record, output, ensure_ascii=False, indent=2)
    output.write("\n")
assert count == 6 and result["results"][0]["year"] >= 2020
print(json.dumps({"imported": count, "result_count": result["result_count"], "status": "passed"}))
