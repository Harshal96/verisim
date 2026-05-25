from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import Date, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from verisim.integrations import UnsupportedIntegrationFieldError
from verisim.integrations.sqlalchemy import verisim_factory


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    organization: Mapped[Organization] = relationship()
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column(String(40), nullable=False)
    last_name: Mapped[str] = mapped_column(String(40), nullable=False)
    birthday: Mapped[date] = mapped_column(Date, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)


class UnsupportedRequired(Base):
    __tablename__ = "unsupported_required"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload: Mapped[bytes] = mapped_column(nullable=False)


def test_sqlalchemy_factory_builds_unpersisted_instance_with_required_parent():
    factory = verisim_factory(User, seed=123)

    user = factory.build()

    assert isinstance(user, User)
    assert user.id is None
    assert user.organization_id is None
    assert isinstance(user.organization, Organization)
    assert user.organization.id is None
    assert user.organization.name
    assert user.organization.domain.endswith(".example.invalid")
    assert user.email.endswith(".example.invalid")
    assert user.username
    assert user.first_name
    assert user.last_name
    assert isinstance(user.birthday, date)
    assert user.nickname is None


def test_sqlalchemy_factory_overrides_values_and_can_add_to_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = verisim_factory(User, seed=321)

    with Session(engine) as session:
        user = factory.create(
            session,
            overrides={"email": "fixed@example.invalid", "username": "fixed-user"},
        )
        session.commit()

        saved = session.get(User, user.id)

    assert saved is not None
    assert saved.email == "fixed@example.invalid"
    assert saved.username == "fixed-user"
    assert saved.organization_id is not None


def test_sqlalchemy_factory_exposes_provider_plan():
    factory = verisim_factory(User, seed=123)
    plan = factory.provider_plan()

    assert plan.source_kind == "sqlalchemy"
    assert plan.field("email").semantic == "email"


def test_sqlalchemy_factory_rejects_required_fields_without_safe_generator():
    factory = verisim_factory(UnsupportedRequired, seed=9)

    with pytest.raises(UnsupportedIntegrationFieldError, match="payload"):
        factory.build()
