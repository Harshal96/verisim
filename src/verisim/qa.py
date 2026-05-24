from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypeVar

from pydantic import BaseModel, ValidationError

from verisim.models import (
    Address,
    Company,
    CompanyRecord,
    Contact,
    Dataset,
    EventRecord,
    GeoPoint,
    MedicalRecord,
    OrderRecord,
    PersonRecord,
    Product,
    ProductRecord,
    ReviewRecord,
    SupportTicketRecord,
    TransactionRecord,
    Website,
)

T = TypeVar("T")

EdgeCase = Literal["empty", "max_length", "nul", "rtl", "negative", "epoch_zero"]

EDGE_CASES: set[str] = {
    "empty",
    "max_length",
    "nul",
    "rtl",
    "negative",
    "epoch_zero",
}
QA_MODES: set[str] = {"edge_cases", "schema_violations"}


def is_qa_mode(mode: str) -> bool:
    return mode in QA_MODES


def apply_edge_case(value: T, edge_case: str | None = None) -> T:
    selected = _normalize_edge_case(edge_case)
    if not isinstance(value, BaseModel):
        return value
    return _edge_model(value, selected)  # type: ignore[return-value]


def raise_schema_violation(
    model: type[T], value: T, violation: str | None = None
) -> None:
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise ValueError("schema violation mode requires a Pydantic model")
    if not isinstance(value, BaseModel):
        raise ValueError("schema violation mode requires a Pydantic model instance")

    path = violation or _default_violation_path(type(value))
    payload = value.model_dump(mode="python")
    _set_path(payload, path.split("."), _invalid_value_for_path(path))
    try:
        model.model_validate(payload)
    except ValidationError:
        raise
    raise ValueError(f"schema violation {path!r} did not fail validation")


def duplicate_count(total: int, percent: int) -> int:
    if percent < 0 or percent > 100:
        raise ValueError("duplicate percent must be between 0 and 100")
    if total <= 1 or percent == 0:
        return 0
    count = (total * percent) // 100
    if count == 0:
        count = 1
    return min(total - 1, count)


def inject_duplicates(records: Iterable[T], percent: int) -> list[T]:
    items = list(records)
    count = duplicate_count(len(items), percent)
    if count == 0:
        return items

    original_count = len(items) - count
    originals = items[:original_count]
    duplicates = [
        near_duplicate(originals[index % len(originals)], index + 1)
        for index in range(count)
    ]
    return [*originals, *duplicates]


def near_duplicate(value: T, index: int) -> T:
    if isinstance(value, PersonRecord):
        return _update_model(
            value,
            contact=_duplicate_contact(value.contact, index),
        )
    if isinstance(value, CompanyRecord):
        domain = _duplicate_domain(value.domain, index)
        return _update_model(
            value,
            domain=domain,
            website=Website.from_host(domain),
            linkedin_slug=_suffix_slug(value.linkedin_slug, index),
        )
    if isinstance(value, ProductRecord):
        slug = _suffix_slug(value.slug, index)
        return _update_model(
            value,
            slug=slug,
            website=Website.from_host(value.company.domain, f"/products/{slug}"),
        )
    if isinstance(value, Company):
        domain = _duplicate_domain(value.domain, index)
        return _update_model(value, domain=domain, website=Website.from_host(domain))
    if isinstance(value, Product):
        slug = _suffix_slug(value.slug, index)
        return _update_model(
            value,
            slug=slug,
            website=Website.from_host(value.website.host, f"/products/{slug}"),
        )
    if isinstance(value, BaseModel):
        return _duplicate_generic_model(value, index)  # type: ignore[return-value]
    return value


def _edge_model(model: BaseModel, edge_case: str) -> BaseModel:
    payload = model.model_dump(mode="python")
    model_type = type(model)
    for field_name in model_type.model_fields:
        current = getattr(model, field_name)
        candidate = _edge_value(field_name, current, edge_case)
        if candidate is current:
            continue
        updated = dict(payload)
        updated[field_name] = candidate
        try:
            model_type.model_validate(updated)
        except ValidationError:
            continue
        payload = updated
    return model_type.model_validate(payload)


def _edge_value(field_name: str, value: object, edge_case: str) -> object:
    if isinstance(value, BaseModel):
        return _edge_model(value, edge_case)
    if isinstance(value, list):
        return [_edge_value(field_name, item, edge_case) for item in value]
    if isinstance(value, tuple):
        return tuple(_edge_value(field_name, item, edge_case) for item in value)
    if isinstance(value, str):
        return _edge_string(field_name, value, edge_case)
    if isinstance(value, int) and not isinstance(value, bool):
        if edge_case == "negative":
            return -1
        if edge_case in {"empty", "epoch_zero"}:
            return 0
    if isinstance(value, float):
        if edge_case == "negative":
            return -1.0
        if edge_case in {"empty", "epoch_zero"}:
            return 0.0
    if value is None:
        if edge_case == "negative" and field_name == "geo":
            return GeoPoint(latitude=-1.0, longitude=-1.0)
        if edge_case == "empty" and field_name in {
            "line2",
            "resolution_summary",
        }:
            return ""
        if edge_case == "epoch_zero" and _is_time_field(field_name):
            return _epoch_value(field_name)
    return value


def _edge_string(field_name: str, value: str, edge_case: str) -> str:
    if edge_case == "empty":
        return ""
    if edge_case == "max_length":
        return _max_length_string(field_name, value)
    if edge_case == "nul":
        return "edge\x00case"
    if edge_case == "rtl":
        return "\u202eRTL edge case"
    if edge_case == "epoch_zero" and _is_time_field(field_name):
        return _epoch_value(field_name)
    if edge_case == "negative":
        return value

    if _is_time_field(field_name):
        return _epoch_value(field_name)
    if field_name in {"line2", "bio", "description", "notes"}:
        return ""
    if field_name in {"domain", "host"}:
        return ""
    return value


def _max_length_string(field_name: str, value: str) -> str:
    if field_name in {"country_code", "region_code"}:
        return "ZZ"
    if field_name == "locale":
        return "zz_ZZ"
    if field_name in {"username", "handle", "slug", "linkedin_slug"}:
        return "a" * 63
    if field_name in {"email"}:
        return f"{'a' * 64}@example.invalid"
    if field_name in {"url", "avatar"}:
        return f"https://{'a' * 63}.example.invalid"
    if field_name in {"host", "domain"}:
        return f"{'a' * 63}.example.invalid"
    if _is_time_field(field_name):
        return (
            "9999-12-31T23:59:59+00:00" if field_name.endswith("_at") else "9999-12-31"
        )
    return "x" * max(256, len(value))


def _is_time_field(field_name: str) -> bool:
    return (
        field_name.endswith("_at")
        or field_name.endswith("_date")
        or field_name == "birthdate"
    )


def _epoch_value(field_name: str) -> str:
    if field_name.endswith("_at"):
        return "1970-01-01T00:00:00+00:00"
    return "1970-01-01"


def _normalize_edge_case(edge_case: str | None) -> str:
    if edge_case is None:
        return "mixed"
    if edge_case not in EDGE_CASES:
        raise ValueError(f"unsupported edge case {edge_case!r}")
    return edge_case


def _default_violation_path(model: type[BaseModel]) -> str:
    defaults = {
        Address: "country_code",
        Contact: "email",
        CompanyRecord: "employee_count",
        ProductRecord: "plans",
        PersonRecord: "contact.email",
        OrderRecord: "line_items",
        TransactionRecord: "amount_minor",
        EventRecord: "participants",
        SupportTicketRecord: "requester.contact.email",
        ReviewRecord: "rating",
        MedicalRecord: "diagnoses",
        Dataset: "people",
    }
    if model in defaults:
        return defaults[model]
    if "id" in model.model_fields:
        return "id"
    return next(iter(model.model_fields))


def _invalid_value_for_path(path: str) -> object:
    field_name = path.split(".")[-1]
    if field_name in {"email"}:
        return "not-an-email"
    if field_name in {"country_code", "region_code"}:
        return "USA"
    if field_name in {
        "employee_count",
        "quantity",
        "amount_minor",
        "total_amount_minor",
        "age_years",
        "rating",
    }:
        return -1
    if field_name in {"founded_year", "launch_year"}:
        return 1700
    if field_name in {"plans", "line_items", "participants", "diagnoses", "people"}:
        return []
    if field_name == "id":
        return "not-a-uuid"
    return None


def _set_path(payload: dict[str, object], path: list[str], value: object) -> None:
    cursor: object = payload
    for part in path[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            raise ValueError(f"unsupported violation path {'.'.join(path)!r}")
        cursor = cursor[part]
    if not isinstance(cursor, dict) or path[-1] not in cursor:
        raise ValueError(f"unsupported violation path {'.'.join(path)!r}")
    cursor[path[-1]] = value


def _duplicate_contact(contact: Contact, index: int) -> Contact:
    return _update_model(contact, email=_duplicate_email(contact.email, index))


def _duplicate_email(email: str, index: int) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return email
    return f"{local}+dup{index}@{domain}"


def _duplicate_domain(domain: str, index: int) -> str:
    if not domain:
        return f"duplicate-{index}.example.invalid"
    label, separator, rest = domain.partition(".")
    if not separator:
        return f"{label}-dup{index}.example.invalid"
    return f"{label}-dup{index}.{rest}"


def _suffix_slug(slug: str, index: int) -> str:
    suffix = f"dup{index}"
    max_base_length = 63 - len(suffix) - 1
    base = slug[:max_base_length].rstrip("._-") or "record"
    return f"{base}-{suffix}"


def _duplicate_generic_model(model: BaseModel, index: int) -> BaseModel:
    for field_name in (
        "description",
        "subject",
        "title",
        "notes",
        "body",
        "account_id",
    ):
        value = getattr(model, field_name, None)
        if isinstance(value, str):
            return _update_model(model, **{field_name: f"{value} duplicate {index}"})
    return model.model_copy(deep=True)


def _update_model(model: T, **updates: object) -> T:
    assert isinstance(model, BaseModel)
    payload = model.model_dump(mode="python")
    payload.update(updates)
    return type(model).model_validate(payload)  # type: ignore[return-value]
