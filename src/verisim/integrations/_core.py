from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from hashlib import sha256
from random import Random
from typing import Any
from uuid import UUID

from verisim import CompanyRecord, PersonRecord, Verisim
from verisim.utils import ascii_slug, username_slug


class UnsupportedIntegrationFieldError(ValueError):
    """Raised when an integration cannot safely populate a required field."""

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"cannot generate field {field_name!r}: {reason}")


@dataclass(frozen=True)
class FieldRequest:
    name: str
    model_name: str
    python_type: type[Any] | None = None
    max_length: int | None = None
    nullable: bool = False
    choices: tuple[Any, ...] = ()


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
        if request.choices:
            return request.choices[0]
        value = self._semantic_value(request)
        if value is None:
            value = self._typed_value(request)
        if isinstance(value, str):
            return self._fit_string(value, request)
        return value

    def _semantic_value(self, request: FieldRequest) -> object | None:
        field = _normalized(request.name)
        model = _normalized(request.model_name)
        person = self._person_record()
        company = self._company_record()
        address = person.address

        if "email" in field:
            return person.contact.email
        if "username" in field or field in {"user", "login", "handle"}:
            return person.person.username
        if field in {"first_name", "given_name", "firstname", "given"}:
            return person.person.given_name
        if field in {"last_name", "family_name", "lastname", "surname", "family"}:
            return person.person.family_name
        if "birth" in field or field in {"dob", "date_of_birth"}:
            return _date_value(person.person.birthdate, request.python_type)
        if "phone" in field or "mobile" in field:
            return person.contact.phone.e164
        if "domain" in field:
            return company.domain
        if "website" in field or field.endswith("_url") or field == "url":
            return (
                company.website.url if _is_company_model(model) else person.website.url
            )
        if "postal" in field or "zip" in field:
            return address.postal_code
        if field in {"city", "town"} or field.endswith("_city"):
            return address.city
        if field in {"region", "state", "province"} or field.endswith("_region"):
            return address.region
        if field in {"region_code", "state_code", "province_code"}:
            return address.region_code
        if field in {"country", "country_name"}:
            return address.country
        if field == "country_code" or field.endswith("_country_code"):
            return address.country_code
        if "address" in field or field in {"line1", "street", "street_address"}:
            return address.line1
        if field in {"job_title", "title", "role"}:
            return person.job.title
        if "department" in field:
            return person.job.department
        if field in {"bio", "biography", "about"}:
            return person.bio
        if field in {"description", "summary"}:
            return f"{company.name} builds synthetic demo data for {company.industry}."
        if field in {"slug", "code"}:
            return self._unique_slug(request.name, person.person.username)
        if field == "name" or field.endswith("_name"):
            if _is_company_model(model) or any(
                token in field for token in ("company", "organization", "org")
            ):
                return company.name
            return person.person.name
        return None

    def _typed_value(self, request: FieldRequest) -> object | None:
        python_type = request.python_type
        if python_type is None:
            if request.nullable:
                return None
            raise UnsupportedIntegrationFieldError(
                request.name, "missing Python type metadata"
            )
        if python_type is str:
            return self._unique_slug(request.name, request.name, separator=" ")
        if python_type is int:
            return self._next_int(request.name)
        if python_type is float:
            return round(self.random.uniform(1.0, 999.0), 2)
        if python_type is bool:
            return bool(self.random.getrandbits(1))
        if python_type is Decimal:
            return Decimal(f"{self.random.randint(10, 999)}.00")
        if python_type is date:
            return date.fromisoformat(self._person_record().person.birthdate)
        if python_type is datetime:
            return datetime.combine(
                date.fromisoformat(self._person_record().person.birthdate),
                time(hour=9),
            )
        if python_type is time:
            return time(hour=9)
        if python_type is UUID:
            return self._person_record().id
        if request.nullable:
            return None
        raise UnsupportedIntegrationFieldError(
            request.name, f"unsupported Python type {python_type.__name__}"
        )

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

    def _unique_slug(self, key: str, value: str, *, separator: str = "-") -> str:
        index = self._next_int(key)
        base = username_slug(value, separator=separator)
        return base if index == 1 else f"{base}{separator}{index}"

    def _fit_string(self, value: str, request: FieldRequest) -> str:
        if request.max_length is None or len(value) <= request.max_length:
            return value
        if request.max_length <= 0:
            return ""
        if request.max_length < 8:
            return value[: request.max_length]
        slug = ascii_slug(value)
        if len(slug) <= request.max_length:
            return slug
        return slug[: request.max_length].rstrip("-") or slug[: request.max_length]


def _date_value(value: str, python_type: type[Any] | None) -> object:
    parsed = date.fromisoformat(value)
    if python_type is datetime:
        return datetime.combine(parsed, time(hour=9))
    if python_type is str or python_type is None:
        return parsed.isoformat()
    return parsed


def _is_company_model(model: str) -> bool:
    return any(token in model for token in ("company", "organization", "org", "team"))


def _normalized(value: str) -> str:
    return value.replace("-", "_").replace(" ", "_").lower()
