from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from random import Random
from types import UnionType
from typing import Annotated, Literal, Protocol, TypeVar, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticUndefined

from verisim.distributions import (
    StatisticalProfile,
    StatisticalSampler,
    is_nullable_annotation,
)
from verisim.errors import GenerationResolutionError, ProfileValidationError
from verisim.models import CompanyRecord, PersonRecord
from verisim.registry import UniquenessRegistry
from verisim.semantics import (
    FieldRequest,
    SemanticSources,
    UnsupportedSemanticFieldError,
    semantic_value,
)

NoneType = type(None)
T = TypeVar("T", bound=BaseModel)


class _Unresolved:
    pass


UNRESOLVED = _Unresolved()


@dataclass(frozen=True)
class FieldContext:
    path: str
    field_name: str
    annotation: object
    random: Random
    facts: Mapping[str, object]
    profile: StatisticalProfile
    unresolved: object = UNRESOLVED


class FieldResolver(Protocol):
    def resolve(self, context: FieldContext) -> object: ...


class CustomModelGenerator:
    def __init__(
        self,
        *,
        random: Random,
        registry: UniquenessRegistry,
        facts: dict[str, object],
        sampler: StatisticalSampler,
        profile: StatisticalProfile,
        resolvers: Sequence[FieldResolver],
        semantic_records: Mapping[str, object] | None = None,
        max_depth: int = 8,
    ) -> None:
        self.random = random
        self.registry = registry
        self.facts = facts
        self.sampler = sampler
        self.profile = profile
        self.resolvers = tuple(resolvers)
        self._semantic_records: dict[str, object] = dict(semantic_records or {})
        self._semantic_counters: dict[str, int] = {}
        self.max_depth = max_depth

    def generate(self, model: type[T]) -> T:
        self.profile.validate_null_rates_for_model(model)
        return self._generate_model(model, path="", depth=0)

    def _generate_model(self, model: type[T], path: str, depth: int) -> T:
        if depth > self.max_depth:
            raise GenerationResolutionError(
                f"maximum custom model depth exceeded at {path or model.__name__}"
            )
        payload: dict[str, object] = {}
        for field_name, field_info in model.model_fields.items():
            field_path = f"{path}.{field_name}" if path else field_name
            payload[field_name] = self._generate_field(
                field_path,
                field_name,
                field_info.annotation,
                field_info.default,
                depth,
            )
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise GenerationResolutionError(
                f"could not validate generated {model.__name__}"
            ) from error

    def _generate_field(
        self,
        path: str,
        field_name: str,
        annotation: object,
        default: object,
        depth: int,
    ) -> object:
        profiled = self.sampler.sample_field(
            path,
            self.random,
            self.facts,
            default=lambda: UNRESOLVED,
            annotation=annotation,
        )
        if profiled is not UNRESOLVED:
            return self._validate(path, annotation, profiled)

        context = FieldContext(
            path=path,
            field_name=field_name,
            annotation=annotation,
            random=self.random,
            facts=self.facts,
            profile=self.profile,
        )
        for resolver in self.resolvers:
            resolved = resolver.resolve(context)
            if resolved is not UNRESOLVED:
                return self._validate(path, annotation, resolved)

        if default is not PydanticUndefined:
            return default

        semantic = self._generate_semantic_value(path, field_name, annotation)
        if semantic is not UNRESOLVED:
            return self._validate(path, annotation, semantic)

        return self._generate_annotation(path, field_name, annotation, depth)

    def _generate_semantic_value(
        self, path: str, field_name: str, annotation: object
    ) -> object:
        try:
            return semantic_value(
                FieldRequest(
                    name=field_name,
                    model_name=path.rsplit(".", 1)[0] or "CustomModel",
                    python_type=annotation if isinstance(annotation, type) else None,
                    nullable=is_nullable_annotation(annotation),
                ),
                SemanticSources(
                    person_record=self._person_record,
                    company_record=self._company_record,
                    next_int=self._next_semantic_int,
                    random=self.random,
                ),
            )
        except UnsupportedSemanticFieldError:
            return UNRESOLVED

    def _person_record(self) -> PersonRecord:
        record = self._semantic_records.get("person_record")
        if record is None:
            record = self._generate_annotation(
                "semantic.person_record", "person_record", PersonRecord, 0
            )
            self._semantic_records["person_record"] = record
        assert isinstance(record, PersonRecord)
        return record

    def _company_record(self) -> CompanyRecord:
        record = self._semantic_records.get("company_record")
        if record is None:
            record = self._generate_annotation(
                "semantic.company_record", "company_record", CompanyRecord, 0
            )
            self._semantic_records["company_record"] = record
        assert isinstance(record, CompanyRecord)
        return record

    def _next_semantic_int(self, key: str) -> int:
        value = self._semantic_counters.get(key, 0) + 1
        self._semantic_counters[key] = value
        return value

    def _generate_annotation(
        self,
        path: str,
        field_name: str,
        annotation: object,
        depth: int,
    ) -> object:
        annotation = _unwrap_annotated(annotation)
        origin = get_origin(annotation)
        args = get_args(annotation)

        if is_nullable_annotation(annotation):
            non_null = [argument for argument in args if argument is not NoneType]
            if not non_null:
                return None
            return self._generate_annotation(path, field_name, non_null[0], depth)

        if origin is Literal:
            return self.random.choice(args)
        if origin in {list, Sequence}:
            item_annotation = args[0] if args else str
            length = (
                self.profile.collection_for(path).length
                if self.profile.collection_for(path)
                else 1
            )
            return [
                self._generate_field(
                    f"{path}[]",
                    field_name,
                    item_annotation,
                    PydanticUndefined,
                    depth,
                )
                for _ in range(length)
            ]
        if origin is set:
            item_annotation = args[0] if args else str
            length = (
                self.profile.collection_for(path).length
                if self.profile.collection_for(path)
                else 1
            )
            return {
                self._generate_field(
                    f"{path}[]",
                    field_name,
                    item_annotation,
                    PydanticUndefined,
                    depth,
                )
                for _ in range(length)
            }
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                length = (
                    self.profile.collection_for(path).length
                    if self.profile.collection_for(path)
                    else 1
                )
                return tuple(
                    self._generate_field(
                        f"{path}[]",
                        field_name,
                        args[0],
                        PydanticUndefined,
                        depth,
                    )
                    for _ in range(length)
                )
            return tuple(
                self._generate_annotation(
                    f"{path}.{index}", field_name, argument, depth
                )
                for index, argument in enumerate(args)
            )
        if origin is dict:
            return {}
        if origin in {UnionType, getattr(__import__("typing"), "Union")}:
            for argument in args:
                if argument is NoneType:
                    continue
                try:
                    return self._generate_annotation(path, field_name, argument, depth)
                except GenerationResolutionError:
                    continue
            raise GenerationResolutionError(f"could not resolve union at {path}")

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return self._generate_model(annotation, path, depth + 1)
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return self.random.choice(list(annotation))
        if annotation is UUID:
            return self.registry.uuid(f"custom:{path}")
        if annotation is str:
            index = self.registry.next_index(f"custom:{path}")
            return f"{field_name}-{index + 1}"
        if annotation is int:
            return self.random.randint(0, 100)
        if annotation is float:
            return self.random.random() * 100
        if annotation is bool:
            return bool(self.random.getrandbits(1))
        if annotation is date:
            return date.today()
        if annotation is datetime:
            return datetime.now(UTC).replace(microsecond=0)

        raise GenerationResolutionError(f"no resolver for field {path!r}")

    def _validate(self, path: str, annotation: object, value: object) -> object:
        if value is None and not is_nullable_annotation(annotation):
            raise ProfileValidationError(
                f"field {path!r} is not nullable and cannot use a null rate"
            )
        try:
            return TypeAdapter(annotation).validate_python(value)
        except ValidationError as error:
            raise GenerationResolutionError(
                f"could not validate field {path!r}"
            ) from error


def _unwrap_annotated(annotation: object) -> object:
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return annotation


__all__ = [
    "CustomModelGenerator",
    "FieldContext",
    "FieldResolver",
    "UNRESOLVED",
]
