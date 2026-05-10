from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

import pytest

from verisim import CompanyRecord, DatasetSpec, PersonRecord, Verisim

SIZE_RANGES = {
    "seed": range(1, 11),
    "startup": range(11, 51),
    "SMB": range(51, 251),
    "mid-market": range(251, 1001),
    "enterprise": range(1001, 10001),
}

LEGAL_ENTITY_TYPES = {
    "US": {"LLC", "Inc.", "Corporation"},
    "GB": {"Ltd", "PLC"},
    "CA": {"Ltd.", "Inc.", "Corporation"},
    "AU": {"Pty Ltd", "Ltd"},
    "IN": {"Pvt Ltd", "LLP", "Ltd"},
    "DE": {"GmbH"},
}


@pytest.mark.parametrize(
    "locale", ("en_US", "en_GB", "en_CA", "en_AU", "en_IN", "de_DE")
)
def test_company_record_generates_coherent_layers(locale: str):
    company = Verisim(locale=locale, seed=31).generate(CompanyRecord)

    assert company.name
    assert company.industry
    assert company.founded_year <= date.today().year
    assert (
        company.legal_entity_type
        in LEGAL_ENTITY_TYPES[company.incorporated_in.country_code]
    )
    assert company.headquarters.country_code == company.incorporated_in.country_code
    assert company.employee_count in SIZE_RANGES[company.size_band]
    assert company.revenue_range.annual_min_usd < company.revenue_range.annual_max_usd
    assert company.website.host == company.domain
    assert company.website.url == f"https://{company.domain}"
    assert company.domain.endswith(".example.invalid")
    assert company.linkedin_slug
    assert " " not in company.linkedin_slug
    assert company.departments
    assert len(company.leadership) >= 1
    assert all(member.person.name for member in company.leadership)
    assert all(member.title for member in company.leadership)


def test_company_record_context_drives_employee_email_job_and_department():
    verisim = Verisim(locale="en_US", seed=44)
    company = verisim.generate(CompanyRecord, context={"size_band": "startup"})

    employees = [
        verisim.generate(PersonRecord, context={"company": company}) for _ in range(12)
    ]

    assert all(employee.company.id == company.id for employee in employees)
    assert all(employee.company.domain == company.domain for employee in employees)
    assert all(
        employee.contact.email.endswith(f"@{company.domain}") for employee in employees
    )
    assert all(employee.job.industry == company.industry for employee in employees)
    assert all(employee.job.department in company.departments for employee in employees)

    first_employee = employees[0]
    local_part = first_employee.contact.email.split("@", maxsplit=1)[0]
    assert local_part == _expected_local_part(company, first_employee)


def test_dataset_people_per_company_uses_company_records_and_balanced_departments():
    verisim = Verisim(locale="en_US", seed=57)

    dataset = verisim.dataset(
        DatasetSpec(
            companies=3,
            people_per_company={"seed": 8, "startup": 25, "mid-market": 120},
        )
    )

    companies_by_id = {company.id: company for company in dataset.companies}
    people_by_company: dict[object, list[PersonRecord]] = defaultdict(list)
    for person in dataset.people:
        people_by_company[person.company.id].append(person)

    assert len(dataset.companies) == 3
    assert {company.size_band for company in dataset.companies} == {
        "seed",
        "startup",
        "mid-market",
    }
    assert len(dataset.people) == 153

    for company in dataset.companies:
        employees = people_by_company[company.id]
        assert (
            len(employees)
            == {
                "seed": 8,
                "startup": 25,
                "mid-market": 120,
            }[company.size_band]
        )
        assert all(
            employee.contact.email.endswith(f"@{company.domain}")
            for employee in employees
        )
        assert all(
            employee.job.department in company.departments for employee in employees
        )

    mid_market = next(
        company for company in dataset.companies if company.size_band == "mid-market"
    )
    department_counts = Counter(
        employee.job.department for employee in people_by_company[mid_market.id]
    )
    assert set(department_counts) == set(mid_market.departments)
    assert max(department_counts.values()) - min(department_counts.values()) <= 1
    assert set(companies_by_id) == set(people_by_company)


def _expected_local_part(company: CompanyRecord, employee: PersonRecord) -> str:
    first = employee.person.given_name.lower()
    last = employee.person.family_name.lower()
    if company.email_pattern == "first.last":
        return f"{first}.{last}"
    if company.email_pattern == "flast":
        return f"{first[0]}{last}"
    if company.email_pattern == "first_last":
        return f"{first}_{last}"
    return first
