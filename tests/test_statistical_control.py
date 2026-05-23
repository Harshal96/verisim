from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

import pytest
from pydantic import BaseModel

from verisim import (
    CollectionRule,
    ConditionalRule,
    DatasetSpec,
    DateTimeWindow,
    FieldContext,
    FieldRule,
    NormalInt,
    ParetoInt,
    Predicate,
    ProfileValidationError,
    StatisticalProfile,
    Verisim,
    WeightedChoice,
)
from verisim.models import Company, CompanyRecord, PersonRecord


def test_profile_controls_existing_model_distributions_and_correlations():
    profile = StatisticalProfile(
        fields={
            "person.age": FieldRule(
                distribution=NormalInt(mean=22, stdev=1, minimum=22, maximum=22)
            ),
            "company.size_band": FieldRule(
                distribution=WeightedChoice(values={"enterprise": 1})
            ),
            "company.employee_count": FieldRule(
                distribution=ParetoInt(minimum=1001, shape=1.5, maximum=1001)
            ),
        },
        correlations=[
            ConditionalRule(
                when=[Predicate(path="person.age", op="lte", value=25)],
                apply={
                    "job.level": FieldRule(
                        distribution=WeightedChoice(values={"Junior": 1})
                    )
                },
            )
        ],
    )

    verisim = Verisim(locale="en_US", seed=12, profile=profile)
    person = verisim.generate(PersonRecord)
    company = verisim.generate(CompanyRecord)
    dataset = Verisim(locale="en_US", seed=15).dataset(
        DatasetSpec(people=3, companies=1, profile=profile)
    )

    assert date.today().year - int(person.person.birthdate[:4]) == 22
    assert person.job.level == "Junior"
    assert company.size_band == "enterprise"
    assert company.employee_count == 1001
    assert all(employee.job.level == "Junior" for employee in dataset.people)
    assert {generated.size_band for generated in dataset.companies} == {"enterprise"}


def test_null_rate_applies_to_nullable_fields_and_rejects_required_fields():
    profile = StatisticalProfile(fields={"company.address": FieldRule(null_rate=1.0)})

    company = Verisim(seed=13, profile=profile).generate(Company)

    assert company.address is None

    invalid = StatisticalProfile(fields={"person.name": FieldRule(null_rate=0.25)})
    with pytest.raises(ProfileValidationError, match="person.name"):
        Verisim(seed=13, profile=invalid).generate(PersonRecord)


class AccountOwner(BaseModel):
    name: str
    role: str | None = None


class AuditEvent(BaseModel):
    id: UUID
    amount: int
    channel: Literal["web", "api"]
    created_at: datetime
    owner: AccountOwner
    tags: list[str]


class AuditResolver:
    def resolve(self, context: FieldContext) -> object:
        if context.path == "id":
            return UUID("00000000-0000-0000-0000-000000000123")
        if context.path == "owner.name":
            return "Maya Rao"
        return context.unresolved


def test_custom_pydantic_models_use_profiles_collections_and_resolvers():
    profile = StatisticalProfile(
        fields={
            "amount": FieldRule(
                distribution=ParetoInt(minimum=500, shape=1.4, maximum=500)
            ),
            "channel": FieldRule(distribution=WeightedChoice(values={"api": 1})),
            "created_at": FieldRule(
                distribution=DateTimeWindow(
                    start=datetime(2026, 5, 18, 9, tzinfo=UTC),
                    end=datetime(2026, 5, 22, 17, tzinfo=UTC),
                    weekday_weights={0: 1, 1: 1, 2: 1, 3: 1, 4: 1},
                )
            ),
            "owner.role": FieldRule(null_rate=1.0),
            "tags[]": FieldRule(distribution=WeightedChoice(values={"release": 1})),
        },
        collections={"tags": CollectionRule(length=2)},
    )

    event = Verisim(
        seed=14,
        profile=profile,
        resolvers=[AuditResolver()],
    ).generate(AuditEvent)

    assert event.id == UUID("00000000-0000-0000-0000-000000000123")
    assert event.amount == 500
    assert event.channel == "api"
    assert event.created_at.weekday() in {0, 1, 2, 3, 4}
    assert event.owner.name == "Maya Rao"
    assert event.owner.role is None
    assert event.tags == ["release", "release"]
