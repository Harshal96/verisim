from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from random import Random
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

from verisim.api import Verisim
from verisim.models import CompanyRecord, PersonRecord
from verisim.semantics import (
    FieldRequest,
    SemanticKind,
    SemanticSources,
    classify_field,
    semantic_value,
)

SourceKind = Literal["pydantic", "sqlalchemy", "json_schema"]


@dataclass(frozen=True)
class FieldPlan:
    name: str
    path: str
    semantic: SemanticKind | None
    python_type: type[Any] | None
    required: bool
    nullable: bool
    max_length: int | None = None
    choices: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ProviderPlan:
    source_kind: SourceKind
    model_name: str
    fields: tuple[FieldPlan, ...]

    def field(self, name: str) -> FieldPlan:
        for field in self.fields:
            if field.name == name:
                return field
        raise KeyError(name)


def infer_providers(source: object) -> ProviderPlan:
    if isinstance(source, type) and issubclass(source, BaseModel):
        return _infer_pydantic(source)
    if isinstance(source, Mapping):
        return _infer_json_schema(source)
    sqlalchemy_plan = _try_infer_sqlalchemy(source)
    if sqlalchemy_plan is not None:
        return sqlalchemy_plan
    raise TypeError(
        "source must be a Pydantic model, SQLAlchemy model, or JSON Schema mapping"
    )


def generate_from_schema(
    schema: Mapping[str, object],
    *,
    locale: str = "en_US",
    output_language: str = "en",
    script: str = "latin",
    seed: int | None = None,
    data_pack: str = "lite",
) -> dict[str, object]:
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
        data_pack=data_pack,
    )
    person = verisim.generate(PersonRecord)
    company = verisim.generate(CompanyRecord)
    counters: dict[str, int] = {}
    random = Random(seed)

    def next_int(key: str) -> int:
        value = counters.get(key, 0) + 1
        counters[key] = value
        return value

    sources = SemanticSources(
        person_record=lambda: person,
        company_record=lambda: company,
        next_int=next_int,
        random=random,
    )
    plan = _infer_json_schema(schema)
    return {
        field.name: _value_for_field(field, plan.model_name, sources)
        for field in plan.fields
    }


def _infer_pydantic(model: type[BaseModel]) -> ProviderPlan:
    fields = []
    for name, info in model.model_fields.items():
        annotation = _unwrap_optional(info.annotation)
        request = FieldRequest(
            name=name,
            model_name=model.__name__,
            python_type=annotation if isinstance(annotation, type) else None,
            max_length=_max_length(info.metadata),
            nullable=_is_nullable(info.annotation),
            choices=_literal_choices(info.annotation),
        )
        fields.append(
            FieldPlan(
                name=name,
                path=name,
                semantic=classify_field(request),
                python_type=request.python_type,
                required=info.is_required(),
                nullable=request.nullable,
                max_length=request.max_length,
                choices=request.choices,
            )
        )
    return ProviderPlan(
        source_kind="pydantic", model_name=model.__name__, fields=tuple(fields)
    )


def _infer_json_schema(schema: Mapping[str, object]) -> ProviderPlan:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError("JSON Schema must contain an object 'properties' mapping")
    required = schema.get("required", ())
    required_names = set(required if isinstance(required, list) else ())
    title = schema.get("title")
    model_name = str(title) if title else "JsonSchema"
    fields = []
    for name, raw_property in properties.items():
        if not isinstance(raw_property, Mapping):
            continue
        python_type = _json_schema_python_type(raw_property)
        request = FieldRequest(
            name=str(name),
            model_name=model_name,
            python_type=python_type,
            max_length=_json_int(raw_property.get("maxLength")),
            nullable=_json_schema_nullable(raw_property),
            choices=(
                tuple(raw_property.get("enum", ()))
                if isinstance(raw_property.get("enum"), list)
                else ()
            ),
        )
        fields.append(
            FieldPlan(
                name=str(name),
                path=str(name),
                semantic=classify_field(request),
                python_type=python_type,
                required=str(name) in required_names,
                nullable=request.nullable,
                max_length=request.max_length,
                choices=request.choices,
            )
        )
    return ProviderPlan(
        source_kind="json_schema", model_name=model_name, fields=tuple(fields)
    )


def _try_infer_sqlalchemy(source: object) -> ProviderPlan | None:
    try:
        from sqlalchemy import inspect
    except ImportError:
        return None
    try:
        mapper = inspect(source)
    except Exception:
        return None
    fields = []
    for attribute in mapper.column_attrs:
        column = attribute.columns[0]
        python_type = _column_python_type(column)
        choices = tuple(getattr(column.type, "enums", None) or ())
        request = FieldRequest(
            name=attribute.key,
            model_name=mapper.class_.__name__,
            python_type=python_type,
            max_length=getattr(column.type, "length", None),
            nullable=bool(column.nullable),
            choices=choices,
        )
        fields.append(
            FieldPlan(
                name=attribute.key,
                path=attribute.key,
                semantic=classify_field(request),
                python_type=python_type,
                required=not bool(column.nullable)
                and not _has_default(column)
                and not _is_generated_primary_key(column),
                nullable=bool(column.nullable),
                max_length=request.max_length,
                choices=choices,
            )
        )
    return ProviderPlan(
        source_kind="sqlalchemy",
        model_name=mapper.class_.__name__,
        fields=tuple(fields),
    )


def _value_for_field(
    field: FieldPlan, model_name: str, sources: SemanticSources
) -> object:
    return semantic_value(
        FieldRequest(
            name=field.name,
            model_name=model_name,
            python_type=field.python_type,
            max_length=field.max_length,
            nullable=field.nullable,
            choices=field.choices,
        ),
        sources,
    )


def _json_schema_python_type(schema: Mapping[str, object]) -> type[Any] | None:
    value_type = schema.get("type")
    if isinstance(value_type, list):
        value_type = next((item for item in value_type if item != "null"), None)
    if schema.get("format") == "date-time":
        return datetime
    if schema.get("format") == "date":
        return date
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }.get(value_type)


def _json_schema_nullable(schema: Mapping[str, object]) -> bool:
    value_type = schema.get("type")
    return value_type == "null" or (
        isinstance(value_type, list) and "null" in value_type
    )


def _json_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _column_python_type(column: Any) -> type[Any] | None:
    try:
        return column.type.python_type
    except (AttributeError, NotImplementedError):
        return None


def _has_default(column: Any) -> bool:
    return any(
        value is not None
        for value in (
            getattr(column, "default", None),
            getattr(column, "server_default", None),
            getattr(column, "computed", None),
            getattr(column, "identity", None),
        )
    )


def _is_generated_primary_key(column: Any) -> bool:
    return bool(column.primary_key) and (
        column.autoincrement is True or column.autoincrement == "auto"
    )


def _literal_choices(annotation: object) -> tuple[Any, ...]:
    origin = get_origin(annotation)
    if origin is Literal:
        return get_args(annotation)
    for argument in get_args(annotation):
        if get_origin(argument) is Literal:
            return get_args(argument)
    return ()


def _is_nullable(annotation: object) -> bool:
    return type(None) in get_args(annotation)


def _unwrap_optional(annotation: object) -> object:
    args = tuple(
        argument for argument in get_args(annotation) if argument is not type(None)
    )
    return args[0] if args else annotation


def _max_length(metadata: Sequence[object]) -> int | None:
    for item in metadata:
        value = getattr(item, "max_length", None)
        if isinstance(value, int):
            return value
    return None


__all__ = [
    "FieldPlan",
    "ProviderPlan",
    "SourceKind",
    "generate_from_schema",
    "infer_providers",
]
