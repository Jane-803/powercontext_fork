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
import re
from dataclasses import dataclass
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from powercontext.builtin.artifacts.memory.models import MemoryCitation
from powercontext.builtin.runtime.models import SearchMemoryRequest
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
        reader = PdfReader(io.BytesIO(value.content), strict=True)
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
    source_id = f"pdf:{quote(value.document_id, safe='')}:{value.document_sha256}:{value.page_number}"
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
    "ebitda": ("operating income", "depreciation amortization", "cash flows"),
    "capex": ("capital expenditures", "capital spending"),
    "restructuring": ("restructuring impairment charges",),
    "legal": ("legal proceedings", "litigation"),
    "geographies": ("geographic divisions", "international operations"),
    "margin": ("net revenue", "operating profit"),
}


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Retrieve distinct page-backed Memory entries through the scoped API."""

    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be positive")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    terms = [term for term in re.findall(r"[a-z]+|\d+", question.lower()) if term not in _STOPWORDS]
    queries = [question]
    if terms:
        queries.append(" ".join(dict.fromkeys(terms)))
    expansions = [phrase for term in terms for phrase in _FINANCIAL_EXPANSIONS.get(term, ())]
    queries.extend(expansions)

    pages = []
    for query in dict.fromkeys(queries):
        pages.append(await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=max(limit, 20))))

    citations: list[MemoryCitation] = []
    seen: set[tuple[str, int, str, str]] = set()
    max_hits = max((len(page.hits) for page in pages), default=0)
    for index in range(max_hits):
        for page in pages:
            if index >= len(page.hits):
                continue
            hit = page.hits[index]
            key = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                MemoryCitation(
                    memory_ref=hit.memory_ref,
                    entry_id=hit.entry_id,
                    entry_version_id=hit.entry_version_id,
                )
            )
            if len(citations) == limit:
                return tuple(citations)
    return tuple(citations)


__all__ = [
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "PDF_PAGE_SOURCE_DEFINITION",
    "parse_pdf_document",
    "search_pdf_pages",
]
