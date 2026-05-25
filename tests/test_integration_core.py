from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest

from verisim.integrations import (
    IntegrationValueGenerator,
    UnsupportedIntegrationFieldError,
    stable_seed,
)


def test_stable_seed_is_none_when_base_seed_is_none():
    assert stable_seed(None, "fixture", "node") is None


def test_stable_seed_is_reproducible_for_same_parts():
    first = stable_seed(123, "fixture", "node")
    second = stable_seed(123, "fixture", "node")
    different = stable_seed(123, "fixture", "other")

    assert first == second
    assert first != different


@pytest.mark.parametrize(
    ("name", "model_name", "expected_type"),
    (
        ("email", "User", str),
        ("phone", "User", str),
        ("website_url", "User", str),
        ("website_url", "Organization", str),
        ("postal_code", "User", str),
        ("city", "User", str),
        ("region", "User", str),
        ("region_code", "User", str),
        ("country", "User", str),
        ("country_code", "User", str),
        ("address_line1", "User", str),
        ("job_title", "User", str),
        ("department", "User", str),
        ("bio", "User", str),
        ("description", "Company", str),
        ("slug", "User", str),
        ("name", "User", str),
        ("name", "Organization", str),
    ),
)
def test_value_generator_maps_common_semantic_field_names(
    name: str, model_name: str, expected_type: type[object]
):
    generator = IntegrationValueGenerator(seed=33)

    value = generator.value_for(name=name, model_name=model_name, python_type=str)

    assert isinstance(value, expected_type)
    assert value


def test_value_generator_uses_shared_semantic_value_generation():
    generator = IntegrationValueGenerator(seed=55)

    email = generator.value_for(name="email", model_name="User", python_type=str)
    company = generator.value_for(
        name="company_name",
        model_name="Organization",
        python_type=str,
    )

    assert isinstance(email, str)
    assert email.endswith(".example.invalid")
    assert isinstance(company, str)
    assert company


def test_value_generator_uses_choices_before_semantic_or_type_generation():
    generator = IntegrationValueGenerator(seed=1)

    value = generator.value_for(
        name="status",
        model_name="User",
        python_type=str,
        choices=("active", "paused"),
    )

    assert value == "active"


@pytest.mark.parametrize(
    ("python_type", "expected_type"),
    (
        (str, str),
        (int, int),
        (float, float),
        (bool, bool),
        (Decimal, Decimal),
        (date, date),
        (datetime, datetime),
        (time, time),
        (UUID, UUID),
    ),
)
def test_value_generator_falls_back_to_supported_python_types(
    python_type: type[object], expected_type: type[object]
):
    generator = IntegrationValueGenerator(seed=44)

    value = generator.value_for(
        name="generic_field",
        model_name="Example",
        python_type=python_type,
    )

    assert isinstance(value, expected_type)


def test_value_generator_returns_none_for_nullable_unknown_type():
    generator = IntegrationValueGenerator(seed=1)

    value = generator.value_for(
        name="optional_payload",
        model_name="Example",
        python_type=None,
        nullable=True,
    )

    assert value is None


def test_value_generator_rejects_required_unknown_and_unsupported_types():
    generator = IntegrationValueGenerator(seed=1)

    with pytest.raises(UnsupportedIntegrationFieldError, match="required_payload"):
        generator.value_for(
            name="required_payload",
            model_name="Example",
            python_type=None,
        )

    with pytest.raises(UnsupportedIntegrationFieldError, match="binary_payload"):
        generator.value_for(
            name="binary_payload",
            model_name="Example",
            python_type=bytes,
        )


def test_value_generator_truncates_strings_to_field_length():
    generator = IntegrationValueGenerator(seed=1)

    tiny = generator.value_for(
        name="description",
        model_name="Company",
        python_type=str,
        max_length=4,
    )
    slugged = generator.value_for(
        name="description",
        model_name="Company",
        python_type=str,
        max_length=16,
    )
    empty = generator.value_for(
        name="description",
        model_name="Company",
        python_type=str,
        max_length=0,
    )

    assert len(tiny) <= 4
    assert len(slugged) <= 16
    assert " " not in slugged
    assert empty == ""
