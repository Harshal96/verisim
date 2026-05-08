import re

import pytest

from verisim import (
    Address,
    Contact,
    ContextConflictError,
    DatasetSpec,
    PersonRecord,
    Socials,
    Verisim,
)


def test_person_record_generates_coherent_fields_for_us_lite():
    verisim = Verisim(locale="en_US", output_language="en", seed=7)

    record = verisim.generate(PersonRecord)

    assert record.person.name
    assert record.person.username
    assert any(part.lower() in record.person.username for part in record.person.name.split())
    assert record.contact.email.endswith(".example.invalid")
    assert record.contact.phone.country_code == "US"
    assert record.contact.phone.e164.startswith("+1")
    assert record.address.country_code == "US"
    assert record.address.postal_code in verisim.data.postal_codes_for_city(
        country_code=record.address.country_code,
        region_code=record.address.region_code,
        city=record.address.city,
    )
    assert record.job.title in record.bio
    assert record.company.name in record.bio
    assert record.company.industry == record.job.industry
    assert record.website.host.endswith(".example.invalid")
    assert record.person.username.replace("_", "-") in record.website.host

    social_handles = [
        record.socials.x.handle,
        record.socials.instagram.handle,
        record.socials.linkedin.handle,
        record.socials.github.handle,
    ]
    assert len(set(social_handles)) >= 3
    assert record.socials.linkedin.handle != record.socials.github.handle


def test_indian_locale_can_output_latin_english_names_and_country_correct_phone():
    verisim = Verisim(locale="hi_IN", output_language="en", script="latin", seed=13)

    record = verisim.generate(PersonRecord)

    assert record.address.country_code == "IN"
    assert record.contact.phone.country_code == "IN"
    assert record.contact.phone.e164.startswith("+91")
    assert record.person.given_name in {"Aarav", "Ananya", "Isha", "Kabir", "Meera", "Om", "Prakash", "Rakesh"}
    assert record.person.name.isascii()
    assert record.address.postal_code in verisim.data.postal_codes_for_city(
        country_code="IN",
        region_code=record.address.region_code,
        city=record.address.city,
    )


def test_generate_socials_from_existing_person_record_uses_context_without_copying_all_handles():
    verisim = Verisim(locale="en_US", seed=21)
    record = verisim.generate(PersonRecord)

    socials = verisim.generate(Socials, context=record)

    handles = {
        socials.x.handle,
        socials.instagram.handle,
        socials.linkedin.handle,
        socials.github.handle,
    }
    assert len(handles) >= 3
    assert record.person.given_name.lower() in socials.linkedin.handle
    assert record.person.family_name.lower() in socials.linkedin.handle
    assert socials.github.handle != socials.linkedin.handle


def test_strict_mode_rejects_country_inconsistent_context_and_repair_mode_fixes_it():
    verisim = Verisim(locale="en_US", seed=1)
    address = Address(
        line1="19 Birch Street",
        city="Austin",
        region="Texas",
        region_code="TX",
        postal_code="78701",
        country="United States",
        country_code="US",
    )
    contact = Contact.synthetic(email="rakesh.patel@example.invalid", phone="+91 98765 43210")

    with pytest.raises(ContextConflictError):
        verisim.generate(PersonRecord, context={"address": address, "contact": contact}, mode="strict")

    repaired = verisim.generate(PersonRecord, context={"address": address, "contact": contact}, mode="repair")

    assert repaired.address.country_code == "US"
    assert repaired.contact.phone.country_code == "US"
    assert repaired.contact.phone.e164.startswith("+1")


def test_explain_mode_returns_diagnostics_without_generating_a_record():
    verisim = Verisim(locale="en_US", seed=1)
    address = Address(
        line1="5 Market Street",
        city="San Francisco",
        region="California",
        region_code="CA",
        postal_code="94105",
        country="United States",
        country_code="US",
    )
    contact = Contact.synthetic(email="person@example.invalid", phone="+91 98765 43210")

    diagnostics = verisim.generate(PersonRecord, context={"address": address, "contact": contact}, mode="explain")

    assert diagnostics.ok is False
    assert diagnostics.conflicts
    assert "phone country IN does not match address country US" in diagnostics.conflicts[0].message


def test_dataset_generation_preserves_referential_integrity_and_uniqueness():
    verisim = Verisim(locale="en_US", seed=42)

    dataset = verisim.dataset(DatasetSpec(people=40, companies=6))

    company_ids = {company.id for company in dataset.companies}
    assert len(dataset.people) == 40
    assert len(dataset.companies) == 6
    assert all(person.company.id in company_ids for person in dataset.people)
    assert len({person.id for person in dataset.people}) == 40
    assert len({person.person.username for person in dataset.people}) == 40
    assert len({person.contact.email for person in dataset.people}) == 40
    assert len({person.contact.phone.e164 for person in dataset.people}) == 40


def test_lite_pack_can_generate_10k_unique_people():
    verisim = Verisim(locale="en_US", seed=99)

    people = verisim.records(PersonRecord, count=10_000)

    assert len(people) == 10_000
    assert len({person.id for person in people}) == 10_000
    assert len({person.person.username for person in people}) == 10_000
    assert len({person.contact.email for person in people}) == 10_000
    assert len({person.contact.phone.e164 for person in people}) == 10_000
    assert all(person.contact.email.endswith(".example.invalid") for person in people)


def test_pack_metadata_records_scope_version_and_provenance():
    verisim = Verisim(locale="en_US", seed=5)

    metadata = verisim.data.metadata

    assert metadata.name == "lite"
    assert metadata.version == "0.1.0"
    assert metadata.scope == "US English plus priority-country sample data"
    assert metadata.provenance
    assert metadata.signed is True


def test_json_output_comes_from_pydantic_models():
    verisim = Verisim(locale="en_US", seed=7)

    record = verisim.generate(PersonRecord)
    payload = record.model_dump_json()

    assert '"person"' in payload
    assert '"address"' in payload
    assert re.search(r'"email":"[^"]+\.example\.invalid"', payload)
