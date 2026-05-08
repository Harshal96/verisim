import json
import re
from importlib.resources import files
from zipfile import ZipFile

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
from verisim.data import load_geonames_postal_countries


def test_locale_name_data_comes_from_packaged_json_files():
    locale_files = files("verisim.datasets.locales")
    en_us_payload = json.loads(locale_files.joinpath("en_US.json").read_text())
    en_in_payload = json.loads(locale_files.joinpath("en_IN.json").read_text())
    hi_in_payload = json.loads(locale_files.joinpath("hi_IN.json").read_text())

    verisim = Verisim(locale="en_US", seed=99)
    en_us_names = verisim.data.names_for_locale("en_US", "latin")
    en_in_names = verisim.data.names_for_locale("en_IN", "latin")
    hi_in_names = verisim.data.names_for_locale("hi_IN", "devanagari")

    assert en_us_payload["locale"] == "en_US"
    assert en_us_payload["script"] == "latin"
    assert tuple(en_us_payload["given"]) == en_us_names.given
    assert tuple(en_us_payload["family"]) == en_us_names.family
    assert len(en_us_payload["given"]) == 1_000
    assert len(set(en_us_payload["given"])) == len(en_us_payload["given"])
    assert len(en_us_payload["family"]) == 1_000
    assert len(set(en_us_payload["family"])) == len(en_us_payload["family"])
    assert en_in_payload["locale"] == "en_IN"
    assert en_in_payload["script"] == "latin"
    assert tuple(en_in_payload["given"]) == en_in_names.given
    assert tuple(en_in_payload["family"]) == en_in_names.family
    assert all(name.isascii() for name in en_in_payload["given"])
    assert hi_in_payload["locale"] == "hi_IN"
    assert hi_in_payload["script"] == "devanagari"
    assert tuple(hi_in_payload["given"]) == hi_in_names.given
    assert tuple(hi_in_payload["family"]) == hi_in_names.family
    assert any(not name.isascii() for name in hi_in_payload["given"])


def test_address_data_comes_from_packaged_country_json_files():
    country_files = files("verisim.datasets.countries")
    us_payload = json.loads(country_files.joinpath("US.json").read_text())
    in_payload = json.loads(country_files.joinpath("IN.json").read_text())

    verisim = Verisim(locale="en_US", seed=99)
    us_country = verisim.data.countries["US"]
    in_country = verisim.data.countries["IN"]
    us_postal_codes = [
        postal_code
        for region in us_payload["regions"]
        for city in region["cities"]
        for postal_code in city["postal_codes"]
    ]

    assert us_payload["code"] == us_country.code
    assert us_payload["name"] == us_country.name
    assert tuple(us_payload["street_names"]) == verisim.data.street_names_for_country(
        "US"
    )
    assert len(us_postal_codes) == 20
    assert len(set(us_postal_codes)) == 20
    assert in_payload["code"] == in_country.code
    assert in_payload["name"] == in_country.name


def test_geonames_postal_zip_can_be_read_as_country_address_data(tmp_path):
    archive = tmp_path / "postal.zip"
    rows = [
        "\t".join(
            (
                "US",
                "10001",
                "New York",
                "New York",
                "NY",
                "New York County",
                "061",
                "",
                "",
                "40.750",
                "-73.997",
                "4",
            )
        ),
        "\t".join(
            (
                "US",
                "10003",
                "New York",
                "New York",
                "NY",
                "New York County",
                "061",
                "",
                "",
                "40.731",
                "-73.989",
                "4",
            )
        ),
        "\t".join(
            (
                "IN",
                "400001",
                "Mumbai",
                "Maharashtra",
                "MH",
                "Mumbai",
                "MUM",
                "",
                "",
                "18.938",
                "72.835",
                "4",
            )
        ),
    ]
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("allCountries.txt", "\n".join(rows))

    countries = load_geonames_postal_countries(archive, country_codes={"US", "IN"})

    assert countries["US"].regions[0].cities[0].name == "New York"
    assert countries["US"].regions[0].cities[0].postal_codes == ("10001", "10003")
    assert countries["IN"].regions[0].name == "Maharashtra"
    assert countries["IN"].regions[0].cities[0].postal_codes == ("400001",)


def test_person_record_generates_coherent_fields_for_us_lite():
    verisim = Verisim(locale="en_US", output_language="en", seed=7)

    record = verisim.generate(PersonRecord)

    assert record.person.name
    assert record.person.username
    assert any(
        part.lower() in record.person.username for part in record.person.name.split()
    )
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


def test_en_indian_locale_can_output_latin_names_and_country_correct_phone():
    verisim = Verisim(locale="en_IN", output_language="en", script="latin", seed=13)

    record = verisim.generate(PersonRecord)

    assert record.address.country_code == "IN"
    assert record.contact.phone.country_code == "IN"
    assert record.contact.phone.e164.startswith("+91")
    assert record.person.given_name in {
        "Aarav",
        "Ananya",
        "Isha",
        "Kabir",
        "Meera",
        "Om",
        "Prakash",
        "Rakesh",
    }
    assert record.person.name.isascii()
    assert record.address.postal_code in verisim.data.postal_codes_for_city(
        country_code="IN",
        region_code=record.address.region_code,
        city=record.address.city,
    )


def test_hindi_locale_outputs_hindi_names_and_country_correct_phone():
    verisim = Verisim(locale="hi_IN", output_language="hi", seed=13)

    record = verisim.generate(PersonRecord)

    assert record.address.country_code == "IN"
    assert record.contact.phone.country_code == "IN"
    assert record.person.given_name in {
        "आरव",
        "अनन्या",
        "ईशा",
        "कबीर",
        "मीरा",
        "ओम",
        "प्रकाश",
        "राकेश",
    }
    assert not record.person.name.isascii()


def test_socials_from_person_record_context_do_not_copy_all_handles():
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
    contact = Contact.synthetic(
        email="rakesh.patel@example.invalid", phone="+91 98765 43210"
    )

    with pytest.raises(ContextConflictError):
        verisim.generate(
            PersonRecord,
            context={"address": address, "contact": contact},
            mode="strict",
        )

    repaired = verisim.generate(
        PersonRecord, context={"address": address, "contact": contact}, mode="repair"
    )

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

    diagnostics = verisim.generate(
        PersonRecord, context={"address": address, "contact": contact}, mode="explain"
    )

    assert diagnostics.ok is False
    assert diagnostics.conflicts
    assert (
        "phone country IN does not match address country US"
        in diagnostics.conflicts[0].message
    )


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

    names = verisim.data.names_for_locale("en_US", "latin")
    people = verisim.records(PersonRecord, count=10_000)

    assert len(names.given) == 1_000
    assert len(set(names.given)) == len(names.given)
    assert len(names.family) == 1_000
    assert len(set(names.family)) == len(names.family)
    assert len(people) == 10_000
    assert len({person.id for person in people}) == 10_000
    assert len({person.person.name for person in people}) == 10_000
    assert len({person.person.family_name for person in people}) <= 1_000
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
