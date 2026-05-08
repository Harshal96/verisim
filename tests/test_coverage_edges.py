from __future__ import annotations

import runpy
import sys
from random import Random

import pytest

from verisim import (
    Address,
    Company,
    Contact,
    ContextConflictError,
    DatasetSpec,
    Job,
    Person,
    PersonRecord,
    PhoneNumber,
    Socials,
    UnsupportedModelError,
    Verisim,
    Website,
)
from verisim.ai import OfflineProseAdapter, ProseAdapter
from verisim.context import ContextGraph, GenerationState
from verisim.data import LiteDataPack
from verisim.models import SocialAccount
from verisim.packs import DataPackManager
from verisim.providers import _industry_by_name
from verisim.registry import UniquenessRegistry
from verisim.utils import ascii_slug, choose_weighted, username_slug


def test_example_modules_can_run_as_scripts(capsys):
    for module_name in (
        "examples.basic_person",
        "examples.context_repair",
        "examples.dataset_generation",
    ):
        sys.modules.pop(module_name, None)
        runpy.run_module(module_name, run_name="__main__")

    output = capsys.readouterr().out
    assert '"person"' in output
    assert '"conflicts"' in output
    assert '"companies"' in output


def test_offline_prose_adapter_and_protocol_method_are_exercised():
    record = Verisim(seed=3).generate(PersonRecord)

    prose = OfflineProseAdapter().bio(record.person, record.job, record.company)
    protocol_result = ProseAdapter.bio(object(), record.person, record.job, record.company)

    assert record.person.name in prose
    assert record.job.title in prose
    assert record.company.name in prose
    assert protocol_result is None


def test_invalid_conflict_mode_is_rejected_when_context_has_conflicts():
    verisim = Verisim(seed=1)
    address = Address(
        line1="1 Market Street",
        city="Austin",
        region="Texas",
        region_code="TX",
        postal_code="78701",
        country="United States",
        country_code="US",
    )
    contact = Contact.synthetic(email="person@example.invalid", phone="+91 98765 43210")

    with pytest.raises(ValueError, match="unknown conflict mode"):
        verisim.generate(PersonRecord, context={"address": address, "contact": contact}, mode="mystery")


def test_iter_records_supports_finite_and_open_ended_generation():
    verisim = Verisim(seed=4)

    finite = list(verisim.iter_records(Person, count=2))
    open_ended = verisim.iter_records(Person)

    assert len(finite) == 2
    assert all(isinstance(person, Person) for person in finite)
    assert isinstance(next(open_ended), Person)


def test_dataset_requires_company_pool_when_people_are_requested():
    with pytest.raises(ValueError, match="companies must be at least 1"):
        Verisim(seed=2).dataset(DatasetSpec(people=1, companies=0))


def test_mapping_context_accepts_unknown_keys_with_model_values():
    verisim = Verisim(seed=5)
    address = verisim.generate(Address)

    contact = verisim.generate(Contact, context={"shipping_address": address})

    assert contact.phone.country_code == address.country_code


def test_person_record_context_can_return_record_or_expand_nested_facts():
    verisim = Verisim(seed=6)
    record = verisim.generate(PersonRecord)

    same_record = verisim.generate(PersonRecord, context=record)
    person = verisim.generate(Person, context=record)

    assert same_record is record
    assert person == record.person


def test_object_context_accepts_address_and_company_models():
    verisim = Verisim(seed=7)
    address = verisim.generate(Address)
    company = verisim.generate(Company)

    contact = verisim.generate(Contact, context=address)
    job = verisim.generate(Job, context=company)

    assert contact.phone.country_code == address.country_code
    assert job.company_id == company.id
    assert job.industry == company.industry


def test_invalid_address_and_job_industry_conflicts_can_be_explained_and_repaired():
    verisim = Verisim(seed=8)
    company = verisim.generate(Company)
    invalid_address = Address(
        line1="10 Lake Road",
        city="Austin",
        region="Texas",
        region_code="TX",
        postal_code="94105",
        country="United States",
        country_code="US",
    )
    mismatched_job = Job(
        title="Payments Engineer",
        industry="Financial Services",
        department="Payments",
        level="Senior",
        company_id=company.id,
    )

    diagnostics = verisim.generate(
        PersonRecord,
        context={"address": invalid_address, "company": company, "job": mismatched_job},
        mode="explain",
    )
    repaired = verisim.generate(
        PersonRecord,
        context={"address": invalid_address, "company": company, "job": mismatched_job},
        mode="repair",
    )

    assert {conflict.code for conflict in diagnostics.conflicts} == {
        "address.postal_code",
        "job.company.industry",
    }
    assert repaired.address.postal_code in verisim.data.postal_codes_for_city(
        repaired.address.country_code,
        repaired.address.region_code,
        repaired.address.city,
    )
    assert repaired.job.industry == repaired.company.industry


def test_strict_mode_raises_for_job_company_industry_conflict():
    verisim = Verisim(seed=9)
    company = verisim.generate(Company)
    mismatched_job = Job(
        title="Payments Engineer",
        industry="Financial Services",
        department="Payments",
        level="Senior",
        company_id=company.id,
    )

    with pytest.raises(ContextConflictError, match="job industry"):
        verisim.generate(PersonRecord, context={"company": company, "job": mismatched_job}, mode="strict")


def test_context_graph_reports_unsupported_model_and_missing_provider():
    verisim = Verisim(seed=10)
    state = GenerationState(
        random=Random(1),
        data=verisim.data,
        registry=UniquenessRegistry(),
        locale="en_US",
        output_language="en",
        script="latin",
        facts={},
    )

    with pytest.raises(UnsupportedModelError, match="does not know"):
        verisim.generate(dict)
    with pytest.raises(UnsupportedModelError, match="No provider"):
        ContextGraph(providers=(), targets={str: "missing"}).generate(str, state)


def test_lite_pack_lookup_helpers_cover_missing_cases_and_explicit_country_generation():
    data = LiteDataPack()
    random = Random(11)
    address = data.make_address(random, locale="en_US", country_code="IN")
    unknown_country_address = Address(
        line1="1 Nowhere Road",
        city="Nowhere",
        region="Unknown",
        region_code="NA",
        postal_code="00000",
        country="Neverland",
        country_code="ZZ",
    )
    unknown_city_address = Address(
        line1="2 Nowhere Road",
        city="Missing City",
        region="California",
        region_code="CA",
        postal_code="99999",
        country="United States",
        country_code="US",
    )

    assert data.postal_codes_for_city("US", "CA", "Missing City") == ()
    assert data.city_for_address(unknown_country_address) is None
    assert data.city_for_address(unknown_city_address) is None
    assert data.city_for_address(address) is not None
    assert address.country_code == "IN"


def test_model_helpers_cover_fallback_phone_website_and_social_handles():
    phone = PhoneNumber.from_string("+44 20 7946 0958")
    website = Website.from_host("example.invalid", "about")
    socials = Socials(
        x=SocialAccount(platform="x", handle="avery.reed", url="https://x.com/avery.reed"),
        instagram=SocialAccount(
            platform="instagram",
            handle="avery_reed",
            url="https://instagram.com/avery_reed",
        ),
        linkedin=SocialAccount(
            platform="linkedin",
            handle="avery-reed",
            url="https://linkedin.com/in/avery-reed",
        ),
        github=SocialAccount(platform="github", handle="reedavery", url="https://github.com/reedavery"),
    )

    assert phone.country_code == "US"
    assert phone.e164 == "+442079460958"
    assert str(website) == "https://example.invalid/about"
    assert socials.handles() == ["avery.reed", "avery_reed", "avery-reed", "reedavery"]


def test_data_pack_manager_lists_and_rejects_packs():
    manager = DataPackManager()

    assert manager.available() == ("lite",)
    assert isinstance(manager.load(), LiteDataPack)
    with pytest.raises(ValueError, match="unknown data pack"):
        manager.load("full")


def test_industry_lookup_falls_back_when_company_industry_is_unknown():
    verisim = Verisim(seed=12)
    state = GenerationState(
        random=Random(1),
        data=verisim.data,
        registry=UniquenessRegistry(),
        locale="en_US",
        output_language="en",
        script="latin",
        facts={},
    )

    industry = _industry_by_name(state, "Experimental Fictional Industry")

    assert industry == verisim.data.industries[0]


def test_uniqueness_registry_contains_values_and_reports_exhaustion():
    registry = UniquenessRegistry()

    registry.reserve("email", "a@example.invalid")

    assert registry.contains("email", "a@example.invalid") is True
    with pytest.raises(RuntimeError, match="could not generate unique value"):
        registry.unique("email", lambda attempt: "a@example.invalid", max_attempts=1)


def test_slug_helpers_and_weighted_choice_cover_fallback_paths():
    class HighRandom:
        def randint(self, low: int, high: int) -> int:
            return high + 1

    assert ascii_slug("Rakesh Prakash") == "rakesh-prakash"
    assert ascii_slug("!!!") == "verisim"
    assert username_slug("!!!") == "person"
    assert choose_weighted(Random(1), [("a", 10), ("b", 1)]) == "a"
    assert choose_weighted(HighRandom(), [("fallback", 1)]) == "fallback"
