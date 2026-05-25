from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from verisim.integrations._core import (
    IntegrationValueGenerator,
    UnsupportedIntegrationFieldError,
)
from verisim.introspection import ProviderPlan, infer_providers

try:
    from sqlalchemy import inspect
    from sqlalchemy.orm import RelationshipProperty
except ImportError as error:  # pragma: no cover - exercised without optional extra
    raise ImportError(
        "SQLAlchemy integration requires SQLAlchemy. Install with "
        "'verisim[sqlalchemy]'."
    ) from error

T = TypeVar("T")


def verisim_factory(
    model: type[T],
    *,
    seed: int | None = None,
    locale: str = "en_US",
    output_language: str = "en",
    script: str = "latin",
) -> "SQLAlchemyFactory[T]":
    generator = IntegrationValueGenerator(
        seed=seed,
        locale=locale,
        output_language=output_language,
        script=script,
    )
    return SQLAlchemyFactory(model, generator=generator)


class SQLAlchemyFactory:
    def __init__(
        self,
        model: type[T],
        *,
        generator: IntegrationValueGenerator,
        max_relationship_depth: int = 1,
    ) -> None:
        self.model = model
        self.generator = generator
        self.max_relationship_depth = max_relationship_depth

    def build(
        self,
        *,
        context: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
        _depth: int = 0,
    ) -> T:
        values = self._values(context=context, overrides=overrides, depth=_depth)
        return self.model(**values)

    def create(
        self,
        session,
        *,
        context: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
    ) -> T:
        instance = self.build(context=context, overrides=overrides)
        session.add(instance)
        session.flush()
        return instance

    def provider_plan(self) -> ProviderPlan:
        return infer_providers(self.model)

    def _values(
        self,
        *,
        context: Mapping[str, object] | None,
        overrides: Mapping[str, object] | None,
        depth: int,
    ) -> dict[str, object]:
        mapper = inspect(self.model)
        supplied = {**dict(context or {}), **dict(overrides or {})}
        values: dict[str, object] = {}
        relationship_columns: set[str] = set()

        for relationship in mapper.relationships:
            if not self._should_build_relationship(relationship, supplied, depth):
                continue
            child_factory = SQLAlchemyFactory(
                relationship.mapper.class_,
                generator=self.generator,
                max_relationship_depth=self.max_relationship_depth,
            )
            values[relationship.key] = child_factory.build(
                context=context,
                overrides=None,
                _depth=depth + 1,
            )
            relationship_columns.update(
                column.key for column in relationship.local_columns
            )

        for attribute in mapper.column_attrs:
            column = attribute.columns[0]
            key = attribute.key
            if key in supplied:
                values[key] = supplied[key]
                continue
            if key in relationship_columns or self._should_skip_column(column):
                continue
            if column.nullable:
                values[key] = None
                continue
            values[key] = self.generator.value_for(
                name=key,
                model_name=self.model.__name__,
                python_type=_python_type(column),
                max_length=getattr(column.type, "length", None),
                nullable=column.nullable,
                choices=_choices(column),
            )

        values.update(overrides or {})
        return values

    def _should_build_relationship(
        self,
        relationship: RelationshipProperty,
        supplied: Mapping[str, object],
        depth: int,
    ) -> bool:
        if relationship.key in supplied:
            return False
        if relationship.uselist or relationship.viewonly:
            return False
        if getattr(relationship.direction, "name", "") != "MANYTOONE":
            return False
        if depth >= self.max_relationship_depth:
            return False
        local_columns = tuple(relationship.local_columns)
        if any(column.key in supplied for column in local_columns):
            return False
        return all(
            not column.nullable and not _has_default(column) for column in local_columns
        )

    def _should_skip_column(self, column: Any) -> bool:
        if column.primary_key and (
            column.autoincrement is True or _has_default(column)
        ):
            return True
        return _has_default(column)


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


def _python_type(column: Any) -> type[Any] | None:
    try:
        return column.type.python_type
    except (AttributeError, NotImplementedError):
        return None


def _choices(column: Any) -> tuple[object, ...]:
    enums = getattr(column.type, "enums", None)
    if enums:
        return tuple(enums)
    return ()


__all__ = ["SQLAlchemyFactory", "UnsupportedIntegrationFieldError", "verisim_factory"]
