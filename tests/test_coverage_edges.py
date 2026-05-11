from __future__ import annotations

import json
import runpy
import sys
from random import Random

import pytest

import verisim.locale_loader as locale_loader
from verisim import (
    Address,
    Company,
    CompanyRecord,
    Contact,
    ContextConflictError,
    DatasetSpec,
    IncorporationJurisdiction,
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
from verisim.data import IndustryData, LiteDataPack, NameData
from verisim.models import SocialAccount
from verisim.packs import DataPackManager
from verisim.providers import (
    CompanyRecordProvider,
    IndustryProvider,
    PersonProvider,
    _industry_by_name,
)
from verisim.registry import UniquenessRegistry
from verisim.utils import ascii_slug, choose_weighted, username_slug


def test_example_modules_can_run_as_scripts(capsys):
    for module_name in (
        "examples.basic_person",
        "examples.company_record",
        "examples.context_repair",
        "examples.dataset_generation",
        "examples.product_record",
    ):
        sys.modules.pop(module_name, None)
        runpy.run_module(module_name, run_name="__main__")

    output = capsys.readouterr().out
    assert '"person"' in output
    assert '"leadership"' in output
    assert '"conflicts"' in output
    assert '"companies"' in output
    assert '"plans"' in output


def test_offline_prose_adapter_and_protocol_method_are_exercised():
    record = Verisim(seed=3).generate(PersonRecord)

    prose = OfflineProseAdapter().bio(record.person, record.job, record.company)
    protocol_result = ProseAdapter.bio(
        object(), record.person, record.job, record.company
    )

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
        verisim.generate(
            PersonRecord,
            context={"address": address, "contact": contact},
            mode="mystery",
        )


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


def test_people_per_company_requires_enough_company_records_for_size_bands():
    spec = DatasetSpec(companies=1, people_per_company={"seed": 1, "startup": 1})

    with pytest.raises(ValueError, match="cover every people_per_company size band"):
        Verisim(seed=2).dataset(spec)


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


def test_company_record_context_can_return_record_or_expand_company_facts():
    verisim = Verisim(seed=6)
    record = verisim.generate(CompanyRecord)

    same_record = verisim.generate(CompanyRecord, context=record)
    company = verisim.generate(Company, context=record)

    assert same_record is record
    assert company == record.as_company()


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

    with pytest.raises(ContextConflictError, match="job.company.industry"):
        verisim.generate(
            PersonRecord,
            context={"company": company, "job": mismatched_job},
            mode="strict",
        )


def test_strict_conflict_error_message_omits_user_contact_values():
    verisim = Verisim(locale="en_US", seed=10)
    company = verisim.generate(CompanyRecord)
    contact = Contact.synthetic(
        email="person@outside.example.invalid", phone="+91 98765 43210"
    )

    with pytest.raises(ContextConflictError) as error:
        verisim.generate(
            PersonRecord,
            context={"company": company, "contact": contact},
            mode="strict",
        )

    message = str(error.value)
    assert "contact.email.company_domain" in message
    assert "person@outside.example.invalid" not in message
    assert "+91" not in message
    assert company.domain not in message


def test_company_record_conflicts_are_explained_and_repaired():
    verisim = Verisim(locale="de_DE", seed=11)
    valid_record = verisim.generate(CompanyRecord, context={"size_band": "seed"})
    invalid_record = valid_record.model_copy(
        update={
            "legal_entity_type": "GmbH",
            "employee_count": 100,
            "incorporated_in": IncorporationJurisdiction(
                country="United States",
                country_code="US",
                region="Delaware",
                region_code="DE",
            ),
        }
    )
    contact = Contact.synthetic(
        email="person@outside.example.invalid", phone="+49 30 5550199"
    )

    diagnostics = verisim.generate(
        PersonRecord,
        context={"company": invalid_record, "contact": contact},
        mode="explain",
    )
    repaired = verisim.generate(
        PersonRecord,
        context={"company": invalid_record, "contact": contact},
        mode="repair",
    )

    assert {conflict.code for conflict in diagnostics.conflicts} == {
        "company.legal_entity_type.country",
        "company.incorporated_in.country",
        "company.employee_count.size_band",
        "contact.email.company_domain",
    }
    assert repaired.company.id != invalid_record.id
    assert repaired.contact.email.endswith(f"@{repaired.company.domain}")
    assert repaired.company.address.country_code == repaired.address.country_code


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
    assert data.names_for_locale("es_MX", "latin") != data.names_for_locale(
        "en_US", "latin"
    )
    assert data.names_for_locale("zz_ZZ", "latin") == data.names_for_locale(
        "en_US", "latin"
    )
    assert address.country_code == "IN"


def test_model_helpers_cover_fallback_phone_website_and_social_handles():
    phone = PhoneNumber.from_string("+44 20 7946 0958")
    canadian_phone = PhoneNumber.from_string("+1 416 555 0199")
    australian_phone = PhoneNumber.from_string("+61 2 5555 0199")
    german_phone = PhoneNumber.from_string("+49 30 5550199")
    mexican_phone = PhoneNumber.from_string("+52 55 5555 0199")
    japanese_phone = PhoneNumber.from_string("+81 3 5555 0199")
    french_phone = PhoneNumber.from_string("+33 1 55 55 01 99")
    brazilian_phone = PhoneNumber.from_string("+55 11 5555 0199")
    chinese_phone = PhoneNumber.from_string("+86 10 5555 0199")
    fallback_phone = PhoneNumber.from_string("5550199")
    website = Website.from_host("example.invalid", "about")
    socials = Socials(
        x=SocialAccount(
            platform="x", handle="avery.reed", url="https://x.com/avery.reed"
        ),
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
        github=SocialAccount(
            platform="github", handle="reedavery", url="https://github.com/reedavery"
        ),
    )

    assert phone.country_code == "GB"
    assert phone.e164 == "+442079460958"
    assert canadian_phone.country_code == "CA"
    assert australian_phone.country_code == "AU"
    assert german_phone.country_code == "DE"
    assert mexican_phone.country_code == "MX"
    assert japanese_phone.country_code == "JP"
    assert french_phone.country_code == "FR"
    assert brazilian_phone.country_code == "BR"
    assert chinese_phone.country_code == "CN"
    assert fallback_phone.e164 == "+5550199"
    assert fallback_phone.country_code == "US"
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


def test_provider_fallback_paths_cover_large_name_sets_and_requested_facts():
    verisim = Verisim(seed=13)
    state = GenerationState(
        random=Random(1),
        data=verisim.data,
        registry=UniquenessRegistry(),
        locale="en_US",
        output_language="en",
        script="latin",
        facts={"industry": "Financial Services", "founded_year": 2010},
    )
    names = NameData(
        given=("Avery",),
        family=tuple(f"Family{index}" for index in range(10_000)),
    )
    provider = PersonProvider()

    given_name, family_name = provider._unique_name(state, names)
    for username in (
        "avery.reed",
        "averyreed",
        "avery_reed",
        "areed",
        "avery88",
        "reed.avery",
    ):
        state.registry.reserve("username", username)
    username = provider._username(state, "Avery", "Reed", 1988)
    industry = IndustryProvider().generate(state)["industry_data"]
    founded_year = CompanyRecordProvider()._founded_year(state, None)
    departments = CompanyRecordProvider()._departments(
        IndustryData(
            industry="New Industry",
            departments=("Research",),
            levels=("Senior",),
            titles=("Researcher",),
            company_prefixes=("Example",),
            company_suffixes=("Labs",),
            bio_templates=("{name} works at {company}.",),
        ),
        "enterprise",
    )

    assert given_name == "Avery"
    assert family_name.startswith("Family")
    assert username == "avery.reed6"
    assert getattr(industry, "industry") == "Financial Services"
    assert founded_year == 2010
    assert "Corporate Affairs" in departments


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (
            {
                "locale": "other_LO",
                "script": "latin",
                "given": ["Avery"],
                "family": ["Reed"],
            },
            "does not match",
        ),
        (
            {
                "locale": "en_US",
                "script": "other",
                "given": ["Avery"],
                "family": ["Reed"],
            },
            "does not support",
        ),
        (
            {"locale": "en_US", "script": "latin", "given": [], "family": ["Reed"]},
            "has no given names",
        ),
        (
            {"locale": "en_US", "script": "latin", "given": ["Avery"], "family": []},
            "has no family names",
        ),
        (
            {
                "locale": "en_US",
                "script": "latin",
                "given": ["Avery"],
                "family": ["Reed", "Reed"],
            },
            "contains duplicate family names",
        ),
    ),
)
def test_locale_loader_rejects_invalid_name_payloads(monkeypatch, payload, message):
    class FakeLocales:
        def joinpath(self, name: str) -> object:
            class FakeResource:
                def __init__(self, resource_name: str) -> None:
                    self.name = resource_name

                def read_text(self, encoding: str) -> str:
                    return json.dumps(payload)

            return FakeResource(name)

    locale_loader.load_locale_names.cache_clear()
    monkeypatch.setattr(locale_loader, "files", lambda _: FakeLocales())

    with pytest.raises(ValueError, match=message):
        locale_loader.load_locale_names("en_US", "latin")


def test_locale_loader_rejects_unsupported_locale_before_resource_lookup(monkeypatch):
    class ExplodingLocales:
        def joinpath(self, name: str) -> object:
            raise AssertionError(f"unexpected resource lookup for {name}")

    locale_loader.load_locale_names.cache_clear()
    monkeypatch.setattr(locale_loader, "files", lambda _: ExplodingLocales())

    with pytest.raises(ValueError, match="unsupported locale"):
        locale_loader.load_locale_names("../en_US", "latin")


def test_locale_loader_rejects_unsupported_script_before_resource_lookup(monkeypatch):
    class ExplodingLocales:
        def joinpath(self, name: str) -> object:
            raise AssertionError(f"unexpected resource lookup for {name}")

    locale_loader.load_locale_names.cache_clear()
    monkeypatch.setattr(locale_loader, "files", lambda _: ExplodingLocales())

    with pytest.raises(ValueError, match="unsupported locale/script"):
        locale_loader.load_locale_names("en_US", "../latin")


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
