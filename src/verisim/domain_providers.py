from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from verisim.context import GenerationState
from verisim.models import (
    Company,
    CompanyRecord,
    DiagnosisCodeRecord,
    EventRecord,
    LineItemRecord,
    MedicalRecord,
    OrderRecord,
    PatientDemographics,
    PersonRecord,
    ProductRecord,
    ReviewRecord,
    SupportTicketRecord,
    TransactionRecord,
)
from verisim.types import ReviewSentiment
from verisim.utils import username_slug


def _iso_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_datetime(
    state: GenerationState,
    min_days: int,
    max_days: int,
    *,
    hour_start: int = 8,
    hour_end: int = 17,
) -> datetime:
    day = date.today() + timedelta(days=state.random.randint(min_days, max_days))
    return datetime.combine(
        day,
        time(
            hour=state.random.randint(hour_start, hour_end),
            minute=state.random.choice((0, 15, 30, 45)),
        ),
        tzinfo=timezone.utc,
    )


def _child_state(
    state: GenerationState, facts: dict[str, object] | None = None
) -> GenerationState:
    return GenerationState(
        random=state.random,
        data=state.data,
        registry=state.registry,
        locale=state.locale,
        output_language=state.output_language,
        script=state.script,
        facts={} if facts is None else dict(facts),
    )


def _company_context(
    state: GenerationState, industry_name: str | None = None
) -> tuple[CompanyRecord | None, Company]:
    company_record = state.facts.get("company_record")
    if isinstance(company_record, CompanyRecord):
        return company_record, company_record.as_company()

    company = state.facts.get("company")
    if isinstance(company, Company):
        return None, company

    from verisim.providers import CompanyRecordProvider, IndustryProvider

    facts: dict[str, object] = {}
    if industry_name is not None:
        facts["industry"] = industry_name
    child = _child_state(state, facts)
    child.facts.update(IndustryProvider().generate(child))
    generated = CompanyRecordProvider().generate(child)
    record = generated["company_record"]
    assert isinstance(record, CompanyRecord)
    return record, record.as_company()


def _person_record_for_company(
    state: GenerationState,
    company: Company,
    company_record: CompanyRecord | None = None,
) -> PersonRecord:
    from verisim.providers import (
        AddressProvider,
        AvatarProvider,
        BioProvider,
        ContactProvider,
        JobProvider,
        PersonProvider,
        PersonRecordProvider,
        SocialsProvider,
        WebsiteProvider,
    )

    facts: dict[str, object] = {"company": company, "industry": company.industry}
    if company_record is not None:
        facts["company_record"] = company_record
        facts["size_band"] = company_record.size_band
    child = _child_state(state, facts)
    providers = (
        PersonProvider(),
        AddressProvider(),
        JobProvider(),
        ContactProvider(),
        SocialsProvider(),
        WebsiteProvider(),
        AvatarProvider(),
        BioProvider(),
        PersonRecordProvider(),
    )
    for provider in providers:
        child.facts.update(provider.generate(child))
    record = child.facts["person_record"]
    assert isinstance(record, PersonRecord)
    return record


def _person_context(
    state: GenerationState,
    company: Company,
    company_record: CompanyRecord | None = None,
) -> PersonRecord:
    person_record = state.facts.get("person_record")
    if isinstance(person_record, PersonRecord):
        return person_record
    return _person_record_for_company(state, company, company_record)


def _product_record_for_company(
    state: GenerationState,
    company: Company,
    company_record: CompanyRecord | None = None,
) -> ProductRecord:
    from verisim.providers import ProductRecordProvider, _industry_by_name

    facts: dict[str, object] = {
        "company": company,
        "industry": company.industry,
        "industry_data": _industry_by_name(state, company.industry),
    }
    if company_record is not None:
        facts["company_record"] = company_record
        facts["size_band"] = company_record.size_band
    child = _child_state(state, facts)
    generated = ProductRecordProvider().generate(child)
    record = generated["product_record"]
    assert isinstance(record, ProductRecord)
    return record


def _product_context(
    state: GenerationState,
    company: Company,
    company_record: CompanyRecord | None = None,
) -> ProductRecord:
    product_record = state.facts.get("product_record")
    if isinstance(product_record, ProductRecord):
        return product_record
    return _product_record_for_company(state, company, company_record)


def _currency_for_company(company: Company) -> str:
    country_code = company.address.country_code if company.address is not None else "US"
    return {
        "AU": "AUD",
        "BR": "BRL",
        "CA": "CAD",
        "CN": "CNY",
        "DE": "EUR",
        "FR": "EUR",
        "GB": "GBP",
        "IN": "INR",
        "JP": "JPY",
        "MX": "MXN",
    }.get(country_code, "USD")


DIAGNOSES: tuple[tuple[str, str], ...] = (
    ("E11.9", "Type 2 diabetes mellitus without complications"),
    ("I10", "Essential hypertension"),
    ("J06.9", "Acute upper respiratory infection"),
    ("M54.5", "Low back pain"),
    ("F41.1", "Generalized anxiety disorder"),
    ("R51.9", "Headache"),
    ("K21.9", "Gastro-esophageal reflux disease"),
    ("Z00.00", "General adult medical examination"),
)


EVENT_TIMEZONES = {
    "AU": "Australia/Sydney",
    "BR": "America/Sao_Paulo",
    "CA": "America/Toronto",
    "CN": "Asia/Shanghai",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "GB": "Europe/London",
    "IN": "Asia/Kolkata",
    "JP": "Asia/Tokyo",
    "MX": "America/Mexico_City",
    "US": "America/Chicago",
}


class OrderRecordProvider:
    provides = ("order_record",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        company_record, company = _company_context(state)
        buyer = _person_context(state, company, company_record)
        product = _product_context(state, company, company_record)
        currency = _currency_for_company(company)
        line_items = self._line_items(state, company, company_record, product, currency)
        subtotal = sum(item.line_total_minor for item in line_items)
        discount = self._discount(state, subtotal)
        tax = int((subtotal - discount) * self._tax_rate(company))
        status = self._status(state)
        ordered_at = _relative_datetime(state, -90, -1)
        fulfilled_at = self._fulfilled_at(state, ordered_at, status)
        updated_at = fulfilled_at or ordered_at + timedelta(
            hours=state.random.randint(1, 72)
        )

        record = OrderRecord(
            id=state.registry.uuid("order"),
            buyer=buyer,
            company=company,
            line_items=line_items,
            status=status,
            currency=currency,
            subtotal_amount_minor=subtotal,
            tax_amount_minor=tax,
            discount_amount_minor=discount,
            total_amount_minor=subtotal + tax - discount,
            ordered_at=_iso_datetime(ordered_at),
            updated_at=_iso_datetime(updated_at),
            fulfilled_at=None if fulfilled_at is None else _iso_datetime(fulfilled_at),
        )
        return {"order_record": record}

    def _line_items(
        self,
        state: GenerationState,
        company: Company,
        company_record: CompanyRecord | None,
        first_product: ProductRecord,
        currency: str,
    ) -> list[LineItemRecord]:
        products = [first_product]
        for _ in range(state.random.randint(0, 2)):
            products.append(_product_record_for_company(state, company, company_record))
        return [self._line_item(state, product, currency) for product in products]

    def _line_item(
        self, state: GenerationState, product: ProductRecord, currency: str
    ) -> LineItemRecord:
        plan = state.random.choice(product.plans)
        low = plan.price_range.amount_min_usd * 100
        high = plan.price_range.amount_max_usd * 100
        unit_amount = state.random.randint(low, max(low, high))
        quantity = state.random.randint(1, 4)
        return LineItemRecord(
            id=state.registry.uuid("line_item"),
            product=product.as_product(),
            quantity=quantity,
            unit_amount_minor=unit_amount,
            line_total_minor=quantity * unit_amount,
            currency=currency,
        )

    def _discount(self, state: GenerationState, subtotal: int) -> int:
        if subtotal < 100_000 or state.random.random() > 0.35:
            return 0
        return int(subtotal * state.random.choice((0.05, 0.1, 0.15)))

    def _tax_rate(self, company: Company) -> float:
        country_code = company.address.country_code if company.address else "US"
        return {
            "AU": 0.10,
            "BR": 0.12,
            "CA": 0.05,
            "CN": 0.06,
            "DE": 0.19,
            "FR": 0.20,
            "GB": 0.20,
            "IN": 0.18,
            "JP": 0.10,
            "MX": 0.16,
        }.get(country_code, 0.08)

    def _status(self, state: GenerationState) -> str:
        return state.random.choice(
            ("placed", "paid", "fulfilled", "delivered", "cancelled")
        )

    def _fulfilled_at(
        self, state: GenerationState, ordered_at: datetime, status: str
    ) -> datetime | None:
        if status not in {"fulfilled", "delivered"}:
            return None
        return ordered_at + timedelta(days=state.random.randint(1, 14))


class TransactionRecordProvider:
    provides = ("transaction_record",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        company_record, merchant = _company_context(state)
        account_holder = _person_context(state, merchant, company_record)
        status = state.random.choice(("authorized", "settled", "declined", "flagged"))
        category = self._category(state, merchant)
        amount = self._amount_minor(state, category)
        record = TransactionRecord(
            id=state.registry.uuid("transaction"),
            account_holder=account_holder,
            merchant=merchant,
            account_id=self._account_id(state, account_holder),
            amount_minor=amount,
            currency=_currency_for_company(merchant),
            category=category,
            status=status,
            fraud_flag=status == "flagged",
            occurred_at=_iso_datetime(_relative_datetime(state, -60, 0, hour_end=23)),
            description=f"{merchant.name} {category.replace('_', ' ')} transaction",
        )
        return {"transaction_record": record}

    def _category(self, state: GenerationState, merchant: Company) -> str:
        if merchant.industry == "Financial Services":
            return state.random.choice(("financial_services", "software", "office"))
        if merchant.industry == "Healthcare Technology":
            return state.random.choice(("healthcare", "software", "office"))
        return state.random.choice(
            ("software", "travel", "office", "meals", "utilities")
        )

    def _amount_minor(self, state: GenerationState, category: str) -> int:
        ranges = {
            "financial_services": (2_500, 250_000),
            "healthcare": (5_000, 150_000),
            "software": (1_500, 95_000),
            "travel": (10_000, 500_000),
            "office": (800, 45_000),
            "meals": (1_200, 25_000),
            "utilities": (3_000, 80_000),
        }
        low, high = ranges[category]
        return state.random.randint(low, high)

    def _account_id(self, state: GenerationState, account_holder: PersonRecord) -> str:
        base = username_slug(account_holder.person.username, separator="")
        sequence = state.registry.next_index(f"account:{account_holder.id}")
        return f"acct_{base[:10]}_{sequence:04d}"


class EventRecordProvider:
    provides = ("event_record",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        company_record, company = _company_context(state)
        organizer = _person_context(state, company, company_record)
        participants = self._participants(state, company, company_record, organizer)
        event_type = state.random.choice(
            ("meeting", "appointment", "booking", "webinar", "onsite_visit")
        )
        starts_at = _relative_datetime(state, 1, 45)
        ends_at = starts_at + timedelta(minutes=state.random.choice((30, 45, 60, 90)))
        venue = self._venue(state, company, company_record)
        record = EventRecord(
            id=state.registry.uuid("event"),
            title=self._title(state, event_type, company),
            event_type=event_type,
            status=state.random.choice(("scheduled", "confirmed")),
            company=company,
            organizer=organizer,
            participants=participants,
            venue=venue,
            timezone=EVENT_TIMEZONES.get(venue.country_code, "UTC"),
            starts_at=_iso_datetime(starts_at),
            ends_at=_iso_datetime(ends_at),
            description=(
                f"{event_type.replace('_', ' ').title()} for "
                f"{company.name} with {len(participants)} participants."
            ),
        )
        return {"event_record": record}

    def _participants(
        self,
        state: GenerationState,
        company: Company,
        company_record: CompanyRecord | None,
        organizer: PersonRecord,
    ) -> list[PersonRecord]:
        participants = [organizer]
        for _ in range(state.random.randint(1, 3)):
            participants.append(
                _person_record_for_company(state, company, company_record)
            )
        return participants

    def _venue(
        self,
        state: GenerationState,
        company: Company,
        company_record: CompanyRecord | None,
    ):
        if company_record is not None:
            return company_record.headquarters
        if company.address is not None:
            return company.address
        return state.data.make_address(state.random, state.locale)

    def _title(self, state: GenerationState, event_type: str, company: Company) -> str:
        nouns = {
            "meeting": ("Planning", "Readout", "Review"),
            "appointment": ("Consultation", "Intake", "Follow-up"),
            "booking": ("Reservation", "Site Visit", "Working Session"),
            "webinar": ("Customer Briefing", "Training", "Enablement"),
            "onsite_visit": ("Implementation Visit", "Operations Walkthrough"),
        }
        return f"{company.name} {state.random.choice(nouns[event_type])}"


class SupportTicketRecordProvider:
    provides = ("support_ticket_record",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        company_record, company = _company_context(state)
        requester = _person_context(state, company, company_record)
        assigned_agent = _person_record_for_company(state, company, company_record)
        category = state.random.choice(
            ("access", "billing", "bug", "integration", "performance", "security")
        )
        status = state.random.choice(("open", "pending", "resolved", "closed"))
        opened_at = _relative_datetime(state, -30, -1, hour_end=20)
        first_response_at = opened_at + timedelta(minutes=state.random.randint(10, 240))
        resolved_at = self._resolved_at(state, first_response_at, status)
        record = SupportTicketRecord(
            id=state.registry.uuid("support_ticket"),
            requester=requester,
            company=company,
            assigned_agent=assigned_agent,
            priority=self._priority(state, category),
            category=category,
            status=status,
            subject=self._subject(category),
            description=self._description(category, requester, company),
            opened_at=_iso_datetime(opened_at),
            first_response_at=_iso_datetime(first_response_at),
            resolved_at=None if resolved_at is None else _iso_datetime(resolved_at),
            resolution_summary=(
                None
                if resolved_at is None
                else f"Resolved {category} request for {requester.person.name}."
            ),
        )
        return {"support_ticket_record": record}

    def _priority(self, state: GenerationState, category: str) -> str:
        if category == "security":
            return state.random.choice(("high", "urgent"))
        if category == "bug":
            return state.random.choice(("normal", "high"))
        return state.random.choice(("low", "normal", "high"))

    def _subject(self, category: str) -> str:
        return {
            "access": "User access request",
            "billing": "Invoice and subscription question",
            "bug": "Unexpected workflow behavior",
            "integration": "Integration sync issue",
            "performance": "Slow dashboard response",
            "security": "Security review request",
        }[category]

    def _description(
        self, category: str, requester: PersonRecord, company: Company
    ) -> str:
        return (
            f"{requester.person.name} reported a {category} issue while working "
            f"with {company.name}."
        )

    def _resolved_at(
        self, state: GenerationState, first_response_at: datetime, status: str
    ) -> datetime | None:
        if status not in {"resolved", "closed"}:
            return None
        return first_response_at + timedelta(hours=state.random.randint(1, 96))


class ReviewRecordProvider:
    provides = ("review_record",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        company_record, company = _company_context(state)
        product = _product_context(state, company, company_record)
        reviewer = _person_context(state, company, company_record)
        sentiment = self._sentiment(state)
        rating = self._rating(state, sentiment)
        title, body = self._text(state, sentiment, product)
        record = ReviewRecord(
            id=state.registry.uuid("review"),
            reviewer=reviewer,
            company=company,
            product=product.as_product(),
            rating=rating,
            sentiment=sentiment,
            title=title,
            body=body,
            reviewed_at=_iso_datetime(_relative_datetime(state, -180, -1)),
            verified_purchase=state.random.random() < 0.82,
        )
        return {"review_record": record}

    def _sentiment(self, state: GenerationState) -> ReviewSentiment:
        requested = state.facts.get("review_sentiment")
        if requested in {"critical", "neutral", "positive"}:
            return requested  # type: ignore[return-value]
        return state.random.choice(("critical", "neutral", "positive"))

    def _rating(self, state: GenerationState, sentiment: str) -> int:
        if sentiment == "positive":
            return state.random.choice((4, 5))
        if sentiment == "neutral":
            return 3
        return state.random.choice((1, 2))

    def _text(
        self, state: GenerationState, sentiment: str, product: ProductRecord
    ) -> tuple[str, str]:
        text_by_sentiment = {
            "positive": (
                f"Excellent fit for {product.category}",
                f"{product.name} has been reliable for our team and excellent "
                "for day-to-day workflow coverage.",
            ),
            "neutral": (
                f"Steady {product.category} option",
                f"{product.name} is an adequate, steady tool with useful basics "
                "and a few areas that still need polish.",
            ),
            "critical": (
                f"Limited value for {product.category}",
                f"{product.name} introduced friction for our team and felt "
                "limited in the workflows we needed most.",
            ),
        }
        title, body = text_by_sentiment[sentiment]
        if state.random.random() < 0.5:
            body = f"{body} Support context was clear throughout the evaluation."
        return title, body


class MedicalRecordProvider:
    provides = ("medical_record",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        company_record, provider = _company_context(state, "Healthcare Technology")
        patient = _person_context(state, provider, company_record)
        visit_date = date.today() - timedelta(days=state.random.randint(1, 730))
        diagnoses = self._diagnoses(state)
        follow_up_date = self._follow_up_date(state, visit_date, diagnoses)
        record = MedicalRecord(
            id=state.registry.uuid("medical_record"),
            patient=patient,
            patient_demographics=self._patient_demographics(state, patient),
            provider=provider,
            visit_date=visit_date.isoformat(),
            visit_type=state.random.choice(
                ("primary_care", "urgent_care", "telehealth", "specialist", "follow_up")
            ),
            diagnoses=diagnoses,
            notes=self._notes(patient, diagnoses),
            follow_up_date=None
            if follow_up_date is None
            else follow_up_date.isoformat(),
        )
        return {"medical_record": record}

    def _patient_demographics(
        self, state: GenerationState, patient: PersonRecord
    ) -> PatientDemographics:
        birthdate = date.fromisoformat(patient.person.birthdate)
        today = date.today()
        age = (
            today.year
            - birthdate.year
            - ((today.month, today.day) < (birthdate.month, birthdate.day))
        )
        return PatientDemographics(
            name=patient.person.name,
            birthdate=patient.person.birthdate,
            age_years=age,
            sex=state.random.choice(("female", "male", "nonbinary", "unknown")),
            blood_type=state.random.choice(
                ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
            ),
            country_code=patient.address.country_code,
        )

    def _diagnoses(self, state: GenerationState) -> list[DiagnosisCodeRecord]:
        count = state.random.choice((1, 1, 2))
        start = state.random.randrange(len(DIAGNOSES))
        diagnoses = []
        for index in range(count):
            code, description = DIAGNOSES[(start + index) % len(DIAGNOSES)]
            diagnoses.append(
                DiagnosisCodeRecord(
                    code=code,
                    description=description,
                    clinical_status=state.random.choice(
                        ("active", "resolved", "recurring")
                    ),
                )
            )
        return diagnoses

    def _follow_up_date(
        self,
        state: GenerationState,
        visit_date: date,
        diagnoses: list[DiagnosisCodeRecord],
    ) -> date | None:
        if not any(diagnosis.clinical_status == "active" for diagnosis in diagnoses):
            return None
        return visit_date + timedelta(days=state.random.choice((14, 30, 45, 90)))

    def _notes(
        self, patient: PersonRecord, diagnoses: list[DiagnosisCodeRecord]
    ) -> str:
        diagnosis_text = ", ".join(diagnosis.description for diagnosis in diagnoses)
        return f"{patient.person.name} was seen for {diagnosis_text.lower()}."
