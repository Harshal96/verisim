from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel

from verisim import Verisim
from verisim.semantics import FieldRequest, SemanticKind, classify_field


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("email", "email"),
        ("work_email", "email"),
        ("username", "username"),
        ("first_name", "given_name"),
        ("last_name", "family_name"),
        ("company_name", "company_name"),
        ("organization_domain", "company_domain"),
        ("website_url", "website_url"),
        ("postal_code", "postal_code"),
        ("state_code", "region_code"),
        ("country_code", "country_code"),
        ("birthday", "birthdate"),
    ),
)
def test_classify_field_maps_common_names(name: str, expected: SemanticKind):
    request = FieldRequest(name=name, model_name="User", python_type=str)

    assert classify_field(request) == expected


def test_classify_field_uses_python_type_for_birthdate():
    request = FieldRequest(name="dob", model_name="User", python_type=date)

    assert classify_field(request) == "birthdate"


def test_classify_field_returns_none_for_unknown_field():
    request = FieldRequest(name="opaque_payload", model_name="User", python_type=bytes)

    assert classify_field(request) is None


class CustomerProfile(BaseModel):
    first_name: str
    last_name: str
    email: str
    company_name: str
    city: str
    country_code: str


def test_custom_pydantic_model_uses_semantic_defaults():
    profile = Verisim(locale="en_US", seed=91).generate(CustomerProfile)

    assert profile.first_name
    assert profile.last_name
    assert profile.email.endswith(".example.invalid")
    assert profile.company_name
    assert profile.city
    assert profile.country_code == "US"
