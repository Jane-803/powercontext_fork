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

"""Physical PDF page capture and page-level Memory retrieval."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from powercontext.builtin.artifacts.memory.models import MemoryCitation
from powercontext.builtin.runtime.models import GetMemoryEntryRequest, SearchMemoryRequest
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TextEvidence


class PDFDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)
    text: str


class PDFPageSource(Source):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def _validate_document_id(document_id: str) -> None:
    if not document_id or not document_id.strip() or document_id != document_id.strip():
        raise ValueError("document_id must be a non-empty trimmed string")


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page before exposing any page result."""

    _validate_document_id(value.document_id)
    if not value.content:
        raise ValueError("PDF content must not be empty")
    digest = hashlib.sha256(value.content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(value.content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a password")
        texts = tuple(page.extract_text() or "" for page in reader.pages)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF could not be parsed completely") from error
    if not texts:
        raise ValueError("PDF must contain at least one physical page")
    return tuple(
        PDFPageInput(document_id=value.document_id, document_sha256=digest, page_number=index, text=text)
        for index, text in enumerate(texts, start=1)
    )


def _source_id(value: PDFPageInput) -> str:
    document_key = hashlib.sha256(value.document_id.encode("utf-8")).hexdigest()
    source_id = f"pdf:{document_key}:{value.document_sha256}:{value.page_number}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"PDF page source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return source_id


@dataclass(frozen=True, slots=True)
class _PDFPageProjection:
    name: str = "powercontext.text-evidence"
    version: str = "1"
    source_class: type[PDFPageSource] = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pdf-page",
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


@dataclass(frozen=True, slots=True)
class _PDFPageSourceDefinition:
    name: str = "pdf-page"
    version: str = "1"
    input_class: type[PDFPageInput] = PDFPageInput
    source_class: type[PDFPageSource] = PDFPageSource
    projections: tuple[_PDFPageProjection, ...] = (_PDFPageProjection(),)

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        _validate_document_id(value.document_id)
        source_id = _source_id(value)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
            definition_version=self.version,
            materialization=SourceMaterialization.CAPTURED,
            **value.model_dump(),
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


PDF_PAGE_SOURCE_DEFINITION = _PDFPageSourceDefinition()


_STOPWORDS = frozenset(
    "a an and are as at be by did do does for from has have how if in into is it of on or that the then to was were what when where which who why with".split()
)
_FINANCIAL_EXPANSIONS = {
    "ebitda": ("consolidated statement of income", "operating income", "depreciation amortization", "cash flows"),
    "capex": ("capital expenditures", "capital spending", "purchases property plant equipment"),
    "restructuring": ("restructuring impairment charges",),
    "legal": ("legal proceedings", "litigation"),
    "geographies": ("our divisions", "north america divisions", "geographic divisions", "international operations"),
    "margin": ("consolidated statement of income", "net revenue", "operating profit"),
    "debt": ("long term debt", "short term borrowings", "total debt"),
    "revenue": ("net revenue", "net sales"),
    "sales": ("net sales", "revenue"),
    "inventory": ("inventories", "cost of sales"),
    "tax": ("income taxes", "effective tax rate"),
    "liquidity": ("cash and cash equivalents", "credit facilities"),
    "acquisition": ("business acquisitions", "purchase consideration"),
    "dividend": ("dividends declared", "dividends paid"),
    "employees": ("employees", "workforce"),
    "cash": ("cash flows", "cash and cash equivalents"),
    "ppne": ("property plant equipment net",),
    "ppe": ("property plant equipment",),
    "assets": ("consolidated balance sheet", "total assets"),
    "liabilities": ("consolidated balance sheet", "total liabilities"),
    "equity": ("consolidated balance sheet", "shareholders equity"),
    "profit": ("consolidated statement of income", "operating profit"),
    "earnings": ("consolidated statement of income", "net income"),
    "expenses": ("consolidated statement of income", "operating expenses"),
    "receivable": ("accounts receivable",),
    "payable": ("accounts payable",),
    "goodwill": ("goodwill intangible assets",),
    "lease": ("operating lease", "lease liabilities"),
    "pension": ("pension postretirement benefits",),
}


def _retrieval_queries(question: str) -> tuple[str, ...]:
    terms = [term for term in re.findall(r"[a-z]+|\d+", question.casefold()) if term not in _STOPWORDS]
    unique = tuple(dict.fromkeys(terms))
    queries: list[str] = [question]
    if unique:
        queries.append(" ".join(unique))
    informative = tuple(term for term in unique if len(term) >= 4 or term.isdigit())
    queries.extend(" ".join(informative[index : index + 3]) for index in range(min(len(informative) - 2, 6)))
    queries.extend(informative[:12])
    queries.extend(phrase for term in unique for phrase in _FINANCIAL_EXPANSIONS.get(term, ()))
    return tuple(query for query in dict.fromkeys(queries) if query.strip())


def _rank_candidates(question: str, ranked_hits: list[tuple[int, int, object]]) -> list[object]:
    by_identity: dict[tuple[str, int, str, str], object] = {}
    ranks: defaultdict[tuple[str, int, str, str], float] = defaultdict(float)
    for query_index, rank, hit in ranked_hits:
        key = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
        by_identity[key] = hit
        ranks[key] += 1.0 / (8.0 + rank) + (0.08 if query_index == 0 else 0.0)

    question_terms = set(re.findall(r"[a-z]+|\d+", question.casefold())) - _STOPWORDS
    phrases = {
        phrase
        for term in question_terms
        for phrase in _FINANCIAL_EXPANSIONS.get(term, ())
    }
    normalized_question = " ".join(re.findall(r"[a-z]+|\d+", question.casefold()))
    phrases.update(
        phrase
        for phrase in (
            "statement of income",
            "income statement",
            "statement of cash flows",
            "cash flow statement",
            "legal proceedings",
            "depreciation and amortization",
            "operating income",
        )
        if phrase in normalized_question
    )
    documents = {key: Counter(re.findall(r"[a-z]+|\d+", hit.text.casefold())) for key, hit in by_identity.items()}
    frequencies = Counter(term for terms in documents.values() for term in question_terms if terms[term])
    total = max(len(documents), 1)

    def score(key):
        terms = documents[key]
        normalized_text = " ".join(re.findall(r"[a-z]+|\d+", by_identity[key].text.casefold()))
        lexical = sum(
            (1.0 + math.log1p(terms[term])) * math.log1p(total / (1 + frequencies[term]))
            for term in question_terms
            if terms[term]
        )
        coverage = len(question_terms.intersection(terms)) / max(len(question_terms), 1)
        phrase_score = sum(24.0 + 2.0 * len(phrase.split()) for phrase in phrases if phrase in normalized_text)
        return lexical + 3.0 * coverage + phrase_score + 5.0 * ranks[key]

    return [by_identity[key] for key in sorted(by_identity, key=lambda key: (-score(key), key))]


async def _select_with_page_neighbors(memory, ranked: list[object], limit: int) -> list[object]:
    pool = ranked[: max(80, limit * 8)]
    locations: dict[tuple[str, int], object] = {}
    hit_locations: dict[tuple[str, int, str, str], tuple[str, int]] = {}
    for hit in pool:
        citation = MemoryCitation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )
        entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
        if len(entry.sources) != 1:
            continue
        source_id = entry.sources[0].source_id
        prefix, separator, page = source_id.rpartition(":")
        if not separator or not page.isdigit():
            continue
        location = (prefix, int(page))
        locations[location] = hit
        hit_locations[(hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)] = location

    neighbor_budget = min(6, limit // 3)
    selected = list(ranked[: limit - neighbor_budget])
    selected_ids = {
        (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id) for hit in selected
    }
    anchor_locations = {
        location
        for anchor in selected
        for identity in (
            (anchor.memory_ref.artifact_id, anchor.memory_ref.revision, anchor.entry_id, anchor.entry_version_id),
        )
        if (location := hit_locations.get(identity)) is not None
    }
    neighbors = []
    for rank, hit in enumerate(pool):
        identity = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
        location = hit_locations.get(identity)
        if location is None or identity in selected_ids:
            continue
        distance = min(
            (abs(location[1] - anchor[1]) for anchor in anchor_locations if anchor[0] == location[0]),
            default=999,
        )
        if distance <= 2:
            neighbors.append((rank + 8 * distance, rank, hit))
    for _priority, _rank, neighbor in sorted(neighbors, key=lambda item: (item[0], item[1]))[:neighbor_budget]:
        neighbor_id = (
            neighbor.memory_ref.artifact_id,
            neighbor.memory_ref.revision,
            neighbor.entry_id,
            neighbor.entry_version_id,
        )
        selected.append(neighbor)
        selected_ids.add(neighbor_id)
        if len(selected) == limit:
            return selected
    for hit in ranked:
        identity = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
        if identity not in selected_ids:
            selected.append(hit)
            selected_ids.add(identity)
            if len(selected) == limit:
                break
    return selected


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Retrieve distinct page-backed Memory entries through the scoped API."""

    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be positive")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    queries = _retrieval_queries(question)
    terms = set(re.findall(r"[a-z]+|\d+", question.casefold())) - _STOPWORDS
    expansions = {phrase for term in terms for phrase in _FINANCIAL_EXPANSIONS.get(term, ())}
    ranked_hits: list[tuple[int, int, object]] = []
    expansion_anchors = []
    for query_index, query in enumerate(queries):
        page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=max(limit, 30)))
        ranked_hits.extend((query_index, rank, hit) for rank, hit in enumerate(page.hits, start=1))
        if query in expansions:
            expansion_anchors.extend(page.hits[:2])

    citations: list[MemoryCitation] = []
    ranked = _rank_candidates(question, ranked_hits)
    anchored = []
    anchored_ids = set()
    for hit in (*expansion_anchors[:8], *ranked):
        identity = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
        if identity not in anchored_ids:
            anchored.append(hit)
            anchored_ids.add(identity)
    ranked = anchored
    for hit in await _select_with_page_neighbors(memory, ranked, limit):
        citations.append(
            MemoryCitation(
                memory_ref=hit.memory_ref,
                entry_id=hit.entry_id,
                entry_version_id=hit.entry_version_id,
            )
        )
    return tuple(citations)


__all__ = [
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "PDF_PAGE_SOURCE_DEFINITION",
    "parse_pdf_document",
    "search_pdf_pages",
]
