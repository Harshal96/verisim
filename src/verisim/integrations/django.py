from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from verisim.integrations._core import (
    IntegrationValueGenerator,
    UnsupportedIntegrationFieldError,
)

try:
    from django.db import models
    from django.db.models.fields import NOT_PROVIDED
except ImportError as error:  # pragma: no cover - exercised without optional extra
    raise ImportError(
        "Django integration requires Django. Install with 'verisim[django]'."
    ) from error

T = TypeVar("T")


def verisim_factory(
    model: type[T],
    *,
    seed: int | None = None,
    locale: str = "en_US",
    output_language: str = "en",
    script: str = "latin",
) -> "DjangoFactory[T]":
    generator = IntegrationValueGenerator(
        seed=seed,
        locale=locale,
        output_language=output_language,
        script=script,
    )
    return DjangoFactory(model, generator=generator)


class DjangoFactory:
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
        values = self._values(
            context=context,
            overrides=overrides,
            depth=_depth,
            persist=False,
            using="default",
        )
        return self.model(**values)

    def create(
        self,
        *,
        context: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
        using: str = "default",
    ) -> T:
        values = self._values(
            context=context,
            overrides=overrides,
            depth=0,
            persist=True,
            using=using,
        )
        return self.model._default_manager.db_manager(using).create(**values)

    def _values(
        self,
        *,
        context: Mapping[str, object] | None,
        overrides: Mapping[str, object] | None,
        depth: int,
        persist: bool,
        using: str,
    ) -> dict[str, object]:
        supplied = {**dict(context or {}), **dict(overrides or {})}
        values: dict[str, object] = {}

        for field in self.model._meta.get_fields():
            if not self._is_forward_relation(field):
                continue
            if not self._should_build_relationship(field, supplied, depth):
                continue
            child_factory = DjangoFactory(
                field.remote_field.model,
                generator=self.generator,
                max_relationship_depth=self.max_relationship_depth,
            )
            child = (
                child_factory.create(context=context, using=using)
                if persist
                else child_factory.build(context=context, _depth=depth + 1)
            )
            values[field.name] = child

        for field in self.model._meta.get_fields():
            if not getattr(field, "concrete", False) or self._is_forward_relation(
                field
            ):
                continue
            key = field.name
            if key in supplied:
                values[key] = supplied[key]
                continue
            if getattr(field, "attname", key) in supplied:
                values[getattr(field, "attname")] = supplied[getattr(field, "attname")]
                continue
            if key in values or self._should_skip_field(field):
                continue
            if getattr(field, "null", False):
                values[key] = None
                continue
            values[key] = self.generator.value_for(
                name=key,
                model_name=self.model.__name__,
                python_type=_python_type(field),
                max_length=getattr(field, "max_length", None),
                nullable=getattr(field, "null", False),
                choices=_choices(field),
            )

        values.update(overrides or {})
        return values

    def _should_build_relationship(
        self, field: Any, supplied: Mapping[str, object], depth: int
    ) -> bool:
        if depth >= self.max_relationship_depth:
            return False
        if field.name in supplied or getattr(field, "attname", "") in supplied:
            return False
        if getattr(field, "null", False) or getattr(field, "blank", False):
            return False
        return not _has_default(field)

    def _should_skip_field(self, field: Any) -> bool:
        if getattr(field, "primary_key", False) and getattr(
            field, "auto_created", False
        ):
            return True
        if isinstance(field, models.AutoField):
            return True
        return _has_default(field)

    def _is_forward_relation(self, field: Any) -> bool:
        return bool(
            getattr(field, "is_relation", False)
            and (
                getattr(field, "many_to_one", False)
                or getattr(field, "one_to_one", False)
            )
            and not getattr(field, "auto_created", False)
            and getattr(field, "remote_field", None) is not None
        )


def _has_default(field: Any) -> bool:
    return getattr(field, "default", NOT_PROVIDED) is not NOT_PROVIDED or bool(
        getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False)
    )


def _choices(field: Any) -> tuple[object, ...]:
    choices = getattr(field, "choices", None)
    if not choices:
        return ()
    values: list[object] = []
    for choice, label in choices:
        if isinstance(label, (list, tuple)):
            values.extend(inner_choice for inner_choice, _ in label)
        else:
            values.append(choice)
    return tuple(values)


def _python_type(field: Any) -> type[Any] | None:
    if isinstance(
        field, (models.CharField, models.TextField, models.EmailField, models.URLField)
    ):
        return str
    if isinstance(field, (models.IntegerField, models.AutoField)):
        return int
    if isinstance(field, models.FloatField):
        return float
    if isinstance(field, models.BooleanField):
        return bool
    if isinstance(field, models.DecimalField):
        return Decimal
    if isinstance(field, models.DateTimeField):
        return datetime
    if isinstance(field, models.DateField):
        return date
    if isinstance(field, models.TimeField):
        return time
    if isinstance(field, models.UUIDField):
        return UUID
    if isinstance(field, models.BinaryField):
        return bytes
    return None


__all__ = ["DjangoFactory", "UnsupportedIntegrationFieldError", "verisim_factory"]
