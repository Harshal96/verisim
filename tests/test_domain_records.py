from __future__ import annotations

from datetime import datetime

import pytest

from verisim import (
    CompanyRecord,
    EventRecord,
    MedicalRecord,
    OrderRecord,
    PersonRecord,
    ProductRecord,
    ReviewRecord,
    SupportTicketRecord,
    TransactionRecord,
    Verisim,
)


def test_order_record_links_buyer_products_company_and_totals():
    verisim = Verisim(locale="en_US", seed=201)
    company = verisim.generate(CompanyRecord, context={"size_band": "startup"})
    buyer = verisim.generate(PersonRecord, context={"company": company})
    product = verisim.generate(ProductRecord, context={"company": company})

    order = verisim.generate(
        OrderRecord,
        context={"person_record": buyer, "product_record": product},
    )

    assert order.buyer.id == buyer.id
    assert order.company.id == company.id
    assert order.line_items
    assert order.currency == "USD"
    assert all(item.product.company_id == company.id for item in order.line_items)
    assert all(item.currency == order.currency for item in order.line_items)
    assert all(
        item.line_total_minor == item.quantity * item.unit_amount_minor
        for item in order.line_items
    )
    assert order.subtotal_amount_minor == sum(
        item.line_total_minor for item in order.line_items
    )
    assert order.total_amount_minor == (
        order.subtotal_amount_minor
        + order.tax_amount_minor
        - order.discount_amount_minor
    )
    assert _parse(order.ordered_at) <= _parse(order.updated_at)
    if order.status in {"fulfilled", "delivered"}:
        assert order.fulfilled_at is not None
        assert _parse(order.ordered_at) <= _parse(order.fulfilled_at)


def test_transaction_record_has_fintech_context_and_fraud_state():
    verisim = Verisim(locale="en_US", seed=202)
    merchant = verisim.generate(
        CompanyRecord, context={"industry": "Financial Services"}
    )

    transaction = verisim.generate(TransactionRecord, context={"company": merchant})

    assert transaction.merchant.id == merchant.id
    assert transaction.currency == "USD"
    assert transaction.amount_minor > 0
    assert transaction.account_id.startswith("acct_")
    assert transaction.category
    assert transaction.status in {"authorized", "settled", "declined", "flagged"}
    assert transaction.fraud_flag == (transaction.status == "flagged")
    assert _parse(transaction.occurred_at)


def test_event_record_has_coherent_participants_and_venue():
    event = Verisim(locale="en_US", seed=203).generate(EventRecord)

    participant_ids = {participant.id for participant in event.participants}

    assert event.organizer.id in participant_ids
    assert len(event.participants) >= 2
    assert event.venue.line1
    assert event.timezone
    assert _parse(event.starts_at) < _parse(event.ends_at)


def test_support_ticket_record_links_requester_agent_and_resolution_timeline():
    ticket = Verisim(locale="en_US", seed=204).generate(SupportTicketRecord)

    assert ticket.requester.company.id == ticket.company.id
    assert ticket.assigned_agent.company.id == ticket.company.id
    assert ticket.priority in {"low", "normal", "high", "urgent"}
    assert ticket.category
    assert ticket.subject
    assert _parse(ticket.opened_at) <= _parse(ticket.first_response_at)
    if ticket.resolved_at is None:
        assert ticket.status in {"open", "pending"}
    else:
        assert ticket.status in {"resolved", "closed"}
        assert _parse(ticket.first_response_at) <= _parse(ticket.resolved_at)
        assert ticket.resolution_summary is not None


@pytest.mark.parametrize(
    ("seed", "expected_sentiment"),
    ((205, "positive"), (206, "neutral"), (207, "critical")),
)
def test_review_record_text_sentiment_matches_rating(
    seed: int, expected_sentiment: str
):
    review = Verisim(locale="en_US", seed=seed).generate(
        ReviewRecord, context={"review_sentiment": expected_sentiment}
    )

    assert review.reviewer.id
    assert review.product.company_id == review.company.id
    assert review.sentiment == expected_sentiment
    if expected_sentiment == "positive":
        assert review.rating >= 4
        assert any(word in review.body.lower() for word in ("reliable", "excellent"))
    elif expected_sentiment == "neutral":
        assert review.rating == 3
        assert any(word in review.body.lower() for word in ("adequate", "steady"))
    else:
        assert review.rating <= 2
        assert any(word in review.body.lower() for word in ("friction", "limited"))


def test_medical_record_is_lightweight_and_patient_coherent():
    record = Verisim(locale="en_US", seed=208).generate(MedicalRecord)

    assert record.patient.id
    assert record.patient_demographics.name == record.patient.person.name
    assert record.patient_demographics.birthdate == record.patient.person.birthdate
    assert record.patient_demographics.age_years >= 18
    assert record.visit_date >= record.patient.person.birthdate
    assert record.diagnoses
    assert all(diagnosis.code for diagnosis in record.diagnoses)
    assert all(diagnosis.code_system == "ICD-10-CM" for diagnosis in record.diagnoses)
    assert record.provider.name


@pytest.mark.parametrize(
    "model",
    (
        OrderRecord,
        TransactionRecord,
        EventRecord,
        SupportTicketRecord,
        ReviewRecord,
        MedicalRecord,
    ),
)
def test_new_domain_record_context_returns_same_record(model):
    verisim = Verisim(locale="en_US", seed=209)
    record = verisim.generate(model)

    same_record = verisim.generate(model, context=record)

    assert same_record is record


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
