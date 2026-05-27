from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from random import Random
from typing import Any, Literal
from uuid import UUID

from verisim.models import CompanyRecord, PersonRecord
from verisim.utils import ascii_slug, username_slug

SemanticKind = Literal[
    "email",
    "username",
    "given_name",
    "family_name",
    "full_name",
    "birthdate",
    "phone",
    "company_domain",
    "website_url",
    "postal_code",
    "city",
    "region",
    "region_code",
    "country",
    "country_code",
    "address_line1",
    "job_title",
    "department",
    "bio",
    "description",
    "slug",
    "company_name",
]


@dataclass(frozen=True)
class FieldRequest:
    name: str
    model_name: str
    python_type: type[Any] | None = None
    max_length: int | None = None
    nullable: bool = False
    choices: tuple[Any, ...] = ()


@dataclass(frozen=True)
class SemanticSources:
    person_record: Callable[[], PersonRecord]
    company_record: Callable[[], CompanyRecord]
    next_int: Callable[[str], int]
    random: Random


class UnsupportedSemanticFieldError(ValueError):
    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"cannot generate field {field_name!r}: {reason}")


def classify_field(request: FieldRequest) -> SemanticKind | None:
    field = _normalized(request.name)
    model = _normalized(request.model_name)

    if "email" in field:
        return "email"
    if "username" in field or field in {"user", "login", "handle"}:
        return "username"
    if field in {"first_name", "given_name", "firstname", "given"}:
        return "given_name"
    if field in {"last_name", "family_name", "lastname", "surname", "family"}:
        return "family_name"
    if field in {"name", "full_name"}:
        return "company_name" if _is_company_model(model) else "full_name"
    if field.endswith("_name"):
        company_tokens = ("company", "organization", "org")
        if any(token in field for token in company_tokens):
            return "company_name"
        return "full_name"
    if "birth" in field or field in {"dob", "date_of_birth", "birthday"}:
        return "birthdate"
    if "phone" in field or "mobile" in field:
        return "phone"
    if "domain" in field:
        return "company_domain"
    if "website" in field or field.endswith("_url") or field == "url":
        return "website_url"
    if "postal" in field or "zip" in field:
        return "postal_code"
    if field in {"city", "town"} or field.endswith("_city"):
        return "city"
    if field in {"region", "state", "province"} or field.endswith("_region"):
        return "region"
    if field in {"region_code", "state_code", "province_code"}:
        return "region_code"
    if field in {"country", "country_name"}:
        return "country"
    if field == "country_code" or field.endswith("_country_code"):
        return "country_code"
    if "address" in field or field in {"line1", "street", "street_address"}:
        return "address_line1"
    if field in {"job_title", "title", "role"}:
        return "job_title"
    if "department" in field:
        return "department"
    if field in {"bio", "biography", "about"}:
        return "bio"
    if field in {"description", "summary"}:
        return "description"
    if field in {"slug", "code"}:
        return "slug"
    return None


def semantic_value(request: FieldRequest, sources: SemanticSources) -> object:
    if request.choices:
        return request.choices[0]

    kind = classify_field(request)
    if kind is None:
        return typed_value(request, sources)

    person = sources.person_record()
    company = sources.company_record()
    address = person.address

    values: dict[SemanticKind, object] = {
        "email": person.contact.email,
        "username": person.person.username,
        "given_name": person.person.given_name,
        "family_name": person.person.family_name,
        "full_name": person.person.name,
        "birthdate": _date_value(person.person.birthdate, request.python_type),
        "phone": person.contact.phone.e164,
        "company_domain": company.domain,
        "website_url": (
            company.website.url
            if _is_company_model(request.model_name)
            else person.website.url
        ),
        "postal_code": address.postal_code,
        "city": address.city,
        "region": address.region,
        "region_code": address.region_code,
        "country": address.country,
        "country_code": address.country_code,
        "address_line1": address.line1,
        "job_title": person.job.title,
        "department": person.job.department,
        "bio": person.bio,
        "description": (
            f"{company.name} builds synthetic demo data for {company.industry}."
        ),
        "slug": _unique_slug(sources, request.name, person.person.username),
        "company_name": company.name,
    }
    value = values[kind]
    if isinstance(value, str):
        return fit_string(value, request)
    return value


def typed_value(request: FieldRequest, sources: SemanticSources) -> object:
    python_type = request.python_type
    if python_type is None:
        if request.nullable:
            return None
        raise UnsupportedSemanticFieldError(
            request.name, "missing Python type metadata"
        )
    if python_type is str:
        return fit_string(
            _unique_slug(sources, request.name, request.name, separator=" "), request
        )
    if python_type is int:
        return sources.next_int(request.name)
    if python_type is float:
        return round(sources.random.uniform(1.0, 999.0), 2)
    if python_type is bool:
        return bool(sources.random.getrandbits(1))
    if python_type is Decimal:
        return Decimal(f"{sources.random.randint(10, 999)}.00")
    if python_type is date:
        return date.fromisoformat(sources.person_record().person.birthdate)
    if python_type is datetime:
        return datetime.combine(
            date.fromisoformat(sources.person_record().person.birthdate),
            time(hour=9),
        )
    if python_type is time:
        return time(hour=9)
    if python_type is UUID:
        return sources.person_record().id
    if python_type is list:
        return []
    if python_type is dict:
        return {}
    if request.nullable:
        return None
    raise UnsupportedSemanticFieldError(
        request.name, f"unsupported Python type {python_type.__name__}"
    )


def fit_string(value: str, request: FieldRequest) -> str:
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


def _unique_slug(
    sources: SemanticSources, key: str, value: str, *, separator: str = "-"
) -> str:
    index = sources.next_int(key)
    base = username_slug(value, separator=separator)
    return base if index == 1 else f"{base}{separator}{index}"


def _is_company_model(model: str) -> bool:
    return any(
        token in _normalized(model)
        for token in ("company", "organization", "org", "team")
    )


def _normalized(value: str) -> str:
    return value.replace("-", "_").replace(" ", "_").lower()


__all__ = [
    "FieldRequest",
    "SemanticKind",
    "SemanticSources",
    "UnsupportedSemanticFieldError",
    "classify_field",
    "fit_string",
    "semantic_value",
    "typed_value",
]
