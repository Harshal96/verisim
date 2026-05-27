from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel, Field

from verisim import Verisim, generate_from_schema, infer_providers

sqlalchemy = pytest.importorskip("sqlalchemy")
sqlalchemy_orm = pytest.importorskip("sqlalchemy.orm")


class SignupRecord(BaseModel):
    email: str
    first_name: str
    company_name: str = Field(max_length=80)
    country_code: str


def test_infer_providers_for_pydantic_model():
    plan = infer_providers(SignupRecord)

    assert plan.source_kind == "pydantic"
    assert plan.model_name == "SignupRecord"
    assert plan.field("email").semantic == "email"
    assert plan.field("first_name").semantic == "given_name"
    assert plan.field("company_name").semantic == "company_name"
    assert plan.field("country_code").required is True


def test_generate_custom_pydantic_model_uses_inferred_semantics():
    record = Verisim(locale="en_US", seed=101).generate(SignupRecord)

    assert record.email.endswith(".example.invalid")
    assert record.first_name
    assert record.company_name
    assert record.country_code == "US"


def test_infer_providers_for_json_schema():
    schema = {
        "type": "object",
        "required": ["email", "company_name"],
        "properties": {
            "email": {"type": "string", "format": "email"},
            "company_name": {"type": "string", "maxLength": 80},
            "city": {"type": "string"},
            "age": {"type": "integer"},
        },
    }

    plan = infer_providers(schema)

    assert plan.source_kind == "json_schema"
    assert plan.field("email").semantic == "email"
    assert plan.field("company_name").max_length == 80
    assert plan.field("city").semantic == "city"
    assert plan.field("age").python_type is int


def test_generate_from_json_schema_returns_semantic_payload():
    payload = generate_from_schema(
        {
            "type": "object",
            "required": ["email", "company_name"],
            "properties": {
                "email": {"type": "string", "format": "email"},
                "company_name": {"type": "string"},
                "country_code": {"type": "string"},
            },
        },
        locale="en_US",
        seed=102,
    )

    assert payload["email"].endswith(".example.invalid")
    assert payload["company_name"]
    assert payload["country_code"] == "US"


def test_infer_providers_for_sqlalchemy_model():
    class Base(sqlalchemy_orm.DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "introspection_users"

        id: sqlalchemy_orm.Mapped[int] = sqlalchemy_orm.mapped_column(
            sqlalchemy.Integer,
            primary_key=True,
            autoincrement=True,
        )
        email: sqlalchemy_orm.Mapped[str] = sqlalchemy_orm.mapped_column(
            sqlalchemy.String(120),
            nullable=False,
        )
        first_name: sqlalchemy_orm.Mapped[str] = sqlalchemy_orm.mapped_column(
            sqlalchemy.String(40),
            nullable=False,
        )
        birthday: sqlalchemy_orm.Mapped[date] = sqlalchemy_orm.mapped_column(
            sqlalchemy.Date,
            nullable=False,
        )

    plan = infer_providers(User)

    assert plan.source_kind == "sqlalchemy"
    assert plan.field("email").semantic == "email"
    assert plan.field("first_name").max_length == 40
    assert plan.field("birthday").python_type is date
