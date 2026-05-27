from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from random import Random
from typing import Any

from verisim.api import Verisim
from verisim.models import CompanyRecord, PersonRecord
from verisim.semantics import (
    FieldRequest,
    SemanticSources,
    UnsupportedSemanticFieldError,
    semantic_value,
)


class UnsupportedIntegrationFieldError(ValueError):
    """Raised when an integration cannot safely populate a required field."""

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"cannot generate field {field_name!r}: {reason}")


def stable_seed(seed: int | None, *parts: object) -> int | None:
    if seed is None:
        return None
    payload = ":".join(str(part) for part in (seed, *parts))
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


class IntegrationValueGenerator:
    def __init__(
        self,
        *,
        seed: int | None = None,
        locale: str = "en_US",
        output_language: str = "en",
        script: str = "latin",
    ) -> None:
        self.seed = seed
        self.random = Random(seed)
        self.verisim = Verisim(
            locale=locale,
            output_language=output_language,
            script=script,
            seed=seed,
        )
        self._records: dict[str, object] = {}
        self._counters: dict[str, int] = {}

    def value_for(
        self,
        *,
        name: str,
        model_name: str,
        python_type: type[Any] | None = None,
        max_length: int | None = None,
        nullable: bool = False,
        choices: Iterable[Any] = (),
    ) -> object:
        request = FieldRequest(
            name=name,
            model_name=model_name,
            python_type=python_type,
            max_length=max_length,
            nullable=nullable,
            choices=tuple(choices),
        )
        try:
            return semantic_value(request, self._semantic_sources())
        except UnsupportedSemanticFieldError as error:
            raise UnsupportedIntegrationFieldError(
                error.field_name, error.reason
            ) from error

    def _person_record(self) -> PersonRecord:
        record = self._records.get("person_record")
        if record is None:
            record = self.verisim.generate(PersonRecord)
            self._records["person_record"] = record
        assert isinstance(record, PersonRecord)
        return record

    def _company_record(self) -> CompanyRecord:
        record = self._records.get("company_record")
        if record is None:
            record = self.verisim.generate(CompanyRecord)
            self._records["company_record"] = record
        assert isinstance(record, CompanyRecord)
        return record

    def _next_int(self, key: str) -> int:
        value = self._counters.get(key, 0) + 1
        self._counters[key] = value
        return value

    def _semantic_sources(self) -> SemanticSources:
        return SemanticSources(
            person_record=self._person_record,
            company_record=self._company_record,
            next_int=self._next_int,
            random=self.random,
        )
