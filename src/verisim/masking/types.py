from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

PIIKind = Literal[
    "name",
    "given_name",
    "family_name",
    "email",
    "phone",
    "address",
    "address_line1",
    "city",
    "region",
    "region_code",
    "postal_code",
    "country",
    "country_code",
]


@dataclass(frozen=True)
class PIIColumn:
    name: str
    kind: PIIKind
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MaskingConfig:
    locale: str = "en_US"
    output_language: str = "en"
    script: str = "latin"
    seed: int | None = None
    identity_columns: tuple[str, ...] | None = None
    column_overrides: Mapping[str, PIIKind | None] | None = None
    sample_size: int = 100
    min_confidence: float = 0.65


@dataclass(frozen=True)
class MaskingResult:
    data: Any | None
    columns: tuple[PIIColumn, ...]
    row_count: int
    masked_cell_count: int
    destination_table: str | None = None


@dataclass(frozen=True)
class _MaskedRows:
    rows: list[dict[str, object]]
    columns: tuple[PIIColumn, ...]
    masked_cell_count: int
