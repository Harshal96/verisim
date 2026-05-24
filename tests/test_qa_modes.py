from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from verisim import Address, DatasetSpec, PersonRecord, Verisim


def test_edge_case_mode_returns_valid_record_with_empty_boundary_values():
    record = Verisim(locale="en_US", seed=301).generate(
        PersonRecord,
        mode="edge_cases",
        edge_case="empty",
    )

    assert isinstance(record, PersonRecord)
    assert record.bio == ""
    assert record.company.domain == ""
    assert record.address.line2 == ""


def test_edge_case_mode_supports_explicit_boundary_selectors():
    verisim = Verisim(locale="en_US", seed=302)

    nul_record = verisim.generate(PersonRecord, mode="edge_cases", edge_case="nul")
    rtl_record = verisim.generate(PersonRecord, mode="edge_cases", edge_case="rtl")
    epoch_record = verisim.generate(
        PersonRecord,
        mode="edge_cases",
        edge_case="epoch_zero",
    )
    negative_address = verisim.generate(
        Address, mode="edge_cases", edge_case="negative"
    )

    assert "\x00" in nul_record.bio
    assert "\u202e" in rtl_record.bio
    assert epoch_record.person.birthdate == "1970-01-01"
    assert negative_address.geo is not None
    assert negative_address.geo.latitude < 0
    assert negative_address.geo.longitude < 0


def test_schema_violation_mode_raises_validation_error_for_selected_rule():
    with pytest.raises(ValidationError) as error:
        Verisim(locale="en_US", seed=303).generate(
            PersonRecord,
            mode="schema_violations",
            violation="contact.email",
        )

    assert ("contact", "email") in {
        tuple(issue["loc"]) for issue in error.value.errors()
    }


def test_qa_modes_reject_context_to_keep_boundary_cases_unambiguous():
    address = Verisim(locale="en_US", seed=304).generate(Address)

    with pytest.raises(ValueError, match="context is not supported"):
        Verisim(locale="en_US", seed=304).generate(
            PersonRecord,
            context={"address": address},
            mode="edge_cases",
        )


def test_records_duplicate_percent_keeps_total_and_reuses_ids():
    records = Verisim(locale="en_US", seed=305).records(
        PersonRecord,
        count=5,
        duplicate_percent=40,
    )

    ids = [record.id for record in records]
    duplicate_ids = {id_ for id_, count in Counter(ids).items() if count > 1}
    duplicate_emails = [
        record.contact.email for record in records if record.id in duplicate_ids
    ]

    assert len(records) == 5
    assert len(set(ids)) == 3
    assert len(duplicate_ids) == 2
    assert any("+dup" in email for email in duplicate_emails)


def test_dataset_duplicate_percent_fields_apply_per_collection():
    dataset = Verisim(locale="en_US", seed=306).dataset(
        DatasetSpec(
            people=5,
            companies=4,
            products=4,
            people_duplicate_percent=40,
            companies_duplicate_percent=25,
            products_duplicate_percent=50,
        )
    )

    assert len(dataset.people) == 5
    assert len(dataset.companies) == 4
    assert len(dataset.products) == 4
    assert len({record.id for record in dataset.people}) == 3
    assert len({record.id for record in dataset.companies}) == 3
    assert len({record.id for record in dataset.products}) == 2
    company_ids = {record.id for record in dataset.companies}
    assert all(record.company.id in company_ids for record in dataset.people)
    assert all(record.company.id in company_ids for record in dataset.products)


def test_company_duplicates_are_injected_before_related_records_are_assigned():
    dataset = Verisim(locale="en_US", seed=307).dataset(
        DatasetSpec(
            people=4,
            companies=4,
            products=4,
            companies_duplicate_percent=25,
        )
    )

    company_ids = {record.id for record in dataset.companies}

    assert len(dataset.companies) == 4
    assert len(company_ids) == 3
    assert all(record.company.id in company_ids for record in dataset.people)
    assert all(record.company.id in company_ids for record in dataset.products)
