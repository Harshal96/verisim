from examples import (
    basic_person,
    company_record,
    context_repair,
    dataset_generation,
    event_record,
    medical_record,
    order_record,
    product_record,
    review_record,
    support_ticket_record,
    transaction_record,
)
from verisim import (
    CompanyRecord,
    Dataset,
    EventRecord,
    GenerationDiagnostics,
    MedicalRecord,
    OrderRecord,
    PersonRecord,
    ProductRecord,
    ReviewRecord,
    SupportTicketRecord,
    TransactionRecord,
)


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


def test_product_record_example_returns_a_product_record():
    product = product_record.generate_example(seed=123)

    assert isinstance(product, ProductRecord)
    assert product.company.domain.endswith(".example.invalid")
    assert product.website.host == product.company.domain
    assert product.plans


def test_new_domain_record_examples_return_expected_models():
    examples = (
        (order_record.generate_example, OrderRecord),
        (transaction_record.generate_example, TransactionRecord),
        (event_record.generate_example, EventRecord),
        (support_ticket_record.generate_example, SupportTicketRecord),
        (review_record.generate_example, ReviewRecord),
        (medical_record.generate_example, MedicalRecord),
    )

    for generate_example, expected_model in examples:
        record = generate_example(seed=123)

        assert isinstance(record, expected_model)
