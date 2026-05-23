from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import TypeAlias

from pydantic import BaseModel

from verisim.models import (
    Address,
    Company,
    CompanyRecord,
    Dataset,
    DatasetEvent,
    PersonRecord,
    ProductRecord,
)

from .schema import ExportLayout, SCHEMA_VERSION

Row: TypeAlias = dict[str, object | None]


def events_from_dataset(dataset: Dataset) -> Iterable[DatasetEvent]:
    for company in dataset.companies:
        yield DatasetEvent(kind="company", record=company)
    for person in dataset.people:
        yield DatasetEvent(kind="person", record=person)
    for product in dataset.products:
        yield DatasetEvent(kind="product", record=product)


class DatasetProjector:
    def __init__(
        self,
        layout: ExportLayout,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.layout = layout
        self.metadata = metadata
        self.company_records: dict[str, CompanyRecord] = {}
        self.counts = {"people": 0, "companies": 0, "products": 0}

    def project(self, event: DatasetEvent) -> list[tuple[str, Row]]:
        if event.kind == "company":
            company = event.record
            if not isinstance(company, CompanyRecord):
                raise TypeError("company events must contain CompanyRecord values")
            self.company_records[str(company.id)] = company
            self.counts["companies"] += 1
            if self.layout in {"relational", "both"}:
                return [("companies", company_row(company))]
            return []

        if event.kind == "person":
            person = event.record
            if not isinstance(person, PersonRecord):
                raise TypeError("person events must contain PersonRecord values")
            self.counts["people"] += 1
            rows: list[tuple[str, Row]] = []
            if self.layout in {"relational", "both"}:
                rows.append(("people", person_row(person)))
                rows.extend(
                    ("social_accounts", social_account_row(str(person.id), account))
                    for account in (
                        person.socials.x,
                        person.socials.instagram,
                        person.socials.linkedin,
                        person.socials.github,
                    )
                )
            if self.layout in {"wide", "both"}:
                rows.append(
                    ("people_wide", people_wide_row(person, self.company_records))
                )
            return rows

        if event.kind == "product":
            product = event.record
            if not isinstance(product, ProductRecord):
                raise TypeError("product events must contain ProductRecord values")
            self.counts["products"] += 1
            rows = []
            if self.layout in {"relational", "both"}:
                rows.append(("products", product_row(product)))
                rows.extend(
                    ("product_plans", product_plan_row(str(product.id), plan))
                    for plan in product.plans
                )
            if self.layout in {"wide", "both"}:
                rows.append(
                    ("products_wide", product_wide_row(product, self.company_records))
                )
            return rows

        raise ValueError(f"unsupported dataset event kind {event.kind!r}")

    def metadata_rows(self) -> list[tuple[str, Row]]:
        rows: list[Row] = [
            {"key": "schema_version", "value": SCHEMA_VERSION},
            {"key": "people_count", "value": str(self.counts["people"])},
            {"key": "companies_count", "value": str(self.counts["companies"])},
            {"key": "products_count", "value": str(self.counts["products"])},
        ]
        if self.metadata is not None:
            rows.extend(
                {"key": str(key), "value": "" if value is None else str(value)}
                for key, value in self.metadata.items()
            )
        return [("export_metadata", row) for row in rows]


def company_row(company: CompanyRecord) -> Row:
    return {
        "id": str(company.id),
        "name": company.name,
        "legal_entity_type": company.legal_entity_type,
        "founded_year": company.founded_year,
        "industry": company.industry,
        "size_band": company.size_band,
        "employee_count": company.employee_count,
        "revenue_min_usd": company.revenue_range.annual_min_usd,
        "revenue_max_usd": company.revenue_range.annual_max_usd,
        "revenue_currency": company.revenue_range.currency,
        "funding_stage": company.funding_stage,
        **address_columns("headquarters", company.headquarters),
        "incorporated_country": company.incorporated_in.country,
        "incorporated_country_code": company.incorporated_in.country_code,
        "incorporated_region": company.incorporated_in.region,
        "incorporated_region_code": company.incorporated_in.region_code,
        "domain": company.domain,
        "website_url": company.website.url,
        "website_host": company.website.host,
        "email_pattern": company.email_pattern,
        "linkedin_slug": company.linkedin_slug,
        "departments_json": json_value(company.departments),
        "leadership_json": json_value(company.leadership),
    }


def person_row(person: PersonRecord) -> Row:
    return {
        "id": str(person.id),
        "company_id": str(person.company.id),
        "given_name": person.person.given_name,
        "family_name": person.person.family_name,
        "name": person.person.name,
        "username": person.person.username,
        "birthdate": person.person.birthdate,
        "locale": person.person.locale,
        "email": person.contact.email,
        "phone_e164": person.contact.phone.e164,
        "phone_national": person.contact.phone.national,
        "phone_country_code": person.contact.phone.country_code,
        "phone_country_calling_code": person.contact.phone.country_calling_code,
        **address_columns("address", person.address),
        "job_title": person.job.title,
        "job_industry": person.job.industry,
        "job_department": person.job.department,
        "job_level": person.job.level,
        "job_company_id": (
            None if person.job.company_id is None else str(person.job.company_id)
        ),
        "avatar": person.avatar,
        "website_url": person.website.url,
        "website_host": person.website.host,
        "bio": person.bio,
    }


def product_row(product: ProductRecord) -> Row:
    return {
        "id": str(product.id),
        "company_id": str(product.company.id),
        "name": product.name,
        "slug": product.slug,
        "product_type": product.product_type,
        "lifecycle_stage": product.lifecycle_stage,
        "launch_year": product.launch_year,
        "industry": product.industry,
        "category": product.category,
        "owner_department": product.owner_department,
        "target_departments_json": json_value(product.target_departments),
        "target_size_band": product.target_size_band,
        "description": product.description,
        "website_url": product.website.url,
        "website_host": product.website.host,
        "pricing_model": product.pricing_model,
        "features_json": json_value(product.features),
    }


def product_plan_row(product_id: str, plan) -> Row:
    return {
        "product_id": product_id,
        "sku": plan.sku,
        "name": plan.name,
        "description": plan.description,
        "billing_interval": plan.billing_interval,
        "price_min_usd": plan.price_range.amount_min_usd,
        "price_max_usd": plan.price_range.amount_max_usd,
        "price_currency": plan.price_range.currency,
        "included_features_json": json_value(plan.included_features),
    }


def social_account_row(person_id: str, account) -> Row:
    return {
        "person_id": person_id,
        "platform": account.platform,
        "handle": account.handle,
        "url": account.url,
    }


def people_wide_row(
    person: PersonRecord, companies: Mapping[str, CompanyRecord]
) -> Row:
    return {**person_row(person), **company_wide_columns(person.company, companies)}


def product_wide_row(
    product: ProductRecord, companies: Mapping[str, CompanyRecord]
) -> Row:
    return {**product_row(product), **company_wide_columns(product.company, companies)}


def company_wide_columns(
    company: Company, companies: Mapping[str, CompanyRecord]
) -> Row:
    record = companies.get(str(company.id))
    if record is not None:
        return {
            "company_name": record.name,
            "company_industry": record.industry,
            "company_size_band": record.size_band,
            "company_employee_count": record.employee_count,
            "company_domain": record.domain,
            "company_website_url": record.website.url,
            "company_country_code": record.headquarters.country_code,
            "company_region_code": record.headquarters.region_code,
        }
    return {
        "company_name": company.name,
        "company_industry": company.industry,
        "company_size_band": None,
        "company_employee_count": None,
        "company_domain": company.domain,
        "company_website_url": company.website.url,
        "company_country_code": (
            None if company.address is None else company.address.country_code
        ),
        "company_region_code": (
            None if company.address is None else company.address.region_code
        ),
    }


def address_columns(prefix: str, address: Address) -> Row:
    return {
        f"{prefix}_line1": address.line1,
        f"{prefix}_line2": address.line2,
        f"{prefix}_city": address.city,
        f"{prefix}_region": address.region,
        f"{prefix}_region_code": address.region_code,
        f"{prefix}_postal_code": address.postal_code,
        f"{prefix}_country": address.country,
        f"{prefix}_country_code": address.country_code,
        f"{prefix}_latitude": None if address.geo is None else address.geo.latitude,
        f"{prefix}_longitude": None if address.geo is None else address.geo.longitude,
    }


def json_value(value: object) -> str:
    if isinstance(value, list):
        value = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in value
        ]
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def flatten_record(record: BaseModel) -> Row:
    flattened: Row = {}
    _flatten_value("", record.model_dump(mode="json"), flattened)
    return flattened


def _flatten_value(prefix: str, value: object, flattened: Row) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}_{key}" if prefix else str(key)
            _flatten_value(child_prefix, child, flattened)
        return
    if isinstance(value, list):
        flattened[prefix] = json_value(value)
        return
    flattened[prefix] = value
