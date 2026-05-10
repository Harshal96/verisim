from examples import basic_person, company_record, context_repair, dataset_generation
from verisim import CompanyRecord, Dataset, GenerationDiagnostics, PersonRecord


def test_basic_person_example_returns_a_person_record():
    record = basic_person.generate_example(seed=123)

    assert isinstance(record, PersonRecord)
    assert record.contact.email.endswith(".example.invalid")
    assert record.job.title in record.bio


def test_context_repair_example_returns_diagnostics_and_repaired_record():
    diagnostics, repaired = context_repair.generate_example(seed=123)

    assert isinstance(diagnostics, GenerationDiagnostics)
    assert diagnostics.ok is False
    assert diagnostics.conflicts
    assert isinstance(repaired, PersonRecord)
    assert repaired.address.country_code == repaired.contact.phone.country_code


def test_company_record_example_returns_a_company_record():
    company = company_record.generate_example(seed=123, size_band="startup")

    assert isinstance(company, CompanyRecord)
    assert company.size_band == "startup"
    assert company.domain.endswith(".example.invalid")
    assert company.website.host == company.domain
    assert company.departments
    assert company.leadership


def test_dataset_generation_example_returns_dataset():
    dataset = dataset_generation.generate_example(seed=123, people=5, companies=2)

    assert isinstance(dataset, Dataset)
    assert len(dataset.people) == 5
    assert len(dataset.companies) == 2
