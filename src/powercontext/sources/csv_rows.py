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

"""Captured row-level evidence for offline CSV documents."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TextEvidence


class CSVDocumentInput(BaseModel):
    """One complete CSV document awaiting row-level parsing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One validated CSV record with its original schema and values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """A captured CSV record addressable independently of row order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def _validate_document_id(document_id: str) -> None:
    if not document_id or not document_id.strip() or document_id != document_id.strip():
        raise ValueError("document_id must be non-empty and contain no surrounding whitespace")


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Return the stable, delimiter-safe identity for one CSV row."""

    _validate_document_id(document_id)
    if not primary_key_value or not primary_key_value.strip():
        raise ValueError("primary_key_value must be non-empty")
    source_id = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"CSV row source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return source_id


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Parse and atomically validate a complete UTF-8 CSV document."""

    _validate_document_id(value.document_id)
    if not value.primary_key or not value.primary_key.strip():
        raise ValueError("primary_key must be non-empty")

    try:
        text = value.content.decode("utf-8-sig", errors="strict")
        records = list(csv.reader(io.StringIO(text, newline=""), delimiter=",", quotechar='"', strict=True))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("invalid CSV document") from error

    if not records:
        raise ValueError("CSV document must contain a header")
    columns = tuple(records[0])
    if not columns or any(not column.strip() for column in columns):
        raise ValueError("CSV header columns must be non-empty")
    if len(set(columns)) != len(columns):
        raise ValueError("CSV header columns must be unique")
    try:
        primary_key_index = columns.index(value.primary_key)
    except ValueError:
        raise ValueError("primary_key must exactly match a header column") from None

    parsed: list[CSVRowInput] = []
    seen_keys: set[str] = set()
    for record in records[1:]:
        if not record:
            continue
        if len(record) != len(columns):
            raise ValueError("CSV record width must match the header")
        primary_key_value = record[primary_key_index]
        if not primary_key_value.strip():
            raise ValueError("CSV primary key values must be non-empty")
        if primary_key_value in seen_keys:
            raise ValueError("CSV primary key values must be unique within a document")
        csv_row_source_id(value.document_id, primary_key_value)
        seen_keys.add(primary_key_value)
        parsed.append(
            CSVRowInput(
                document_id=value.document_id,
                primary_key=value.primary_key,
                primary_key_value=primary_key_value,
                columns=columns,
                values=tuple(record),
            )
        )
    return tuple(parsed)


@dataclass(frozen=True, slots=True)
class _CSVRowTextEvidenceProjection:
    name: str = "powercontext.text-evidence"
    version: str = "1"
    source_class: type[CSVRowSource] = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type="csv-row",
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


@dataclass(frozen=True, slots=True)
class _CSVRowSourceDefinition:
    name: str = "csv-row"
    version: str = "1"
    input_class: type[CSVRowInput] = CSVRowInput
    source_class: type[CSVRowSource] = CSVRowSource
    projections: tuple[_CSVRowTextEvidenceProjection, ...] = (_CSVRowTextEvidenceProjection(),)

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        if len(value.columns) != len(value.values):
            raise ValueError("CSV row columns and values must have equal length")
        if len(set(value.columns)) != len(value.columns) or any(not column.strip() for column in value.columns):
            raise ValueError("CSV row columns must be non-empty and unique")
        if value.primary_key not in value.columns:
            raise ValueError("CSV row primary_key must exactly match a column")
        primary_key_index = value.columns.index(value.primary_key)
        if value.values[primary_key_index] != value.primary_key_value:
            raise ValueError("CSV row primary_key_value must match the row value")
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            definition_version=self.version,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


CSV_ROW_SOURCE_DEFINITION = _CSVRowSourceDefinition()


__all__ = [
    "CSVDocumentInput",
    "CSVRowInput",
    "CSVRowSource",
    "CSV_ROW_SOURCE_DEFINITION",
    "csv_row_source_id",
    "parse_csv_document",
]
