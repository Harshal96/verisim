from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SCHEMA_VERSION = "1"
ExportFormat = Literal[
    "json", "jsonl", "csv", "sql", "sqlite", "parquet", "feather", "arrow", "avro"
]
ExportLayout = Literal["relational", "wide", "both"]
SqlMode = Literal["copy", "insert"]


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: Literal["TEXT", "INTEGER", "REAL"]
    nullable: bool = False
    unique: bool = False


@dataclass(frozen=True)
class ForeignKey:
    column: str
    target_table: str
    target_column: str = "id"
    on_delete: str = "RESTRICT"


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    indexes: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


def text(name: str, *, nullable: bool = False, unique: bool = False) -> Column:
    return Column(name=name, sql_type="TEXT", nullable=nullable, unique=unique)


def integer(name: str, *, nullable: bool = False, unique: bool = False) -> Column:
    return Column(name=name, sql_type="INTEGER", nullable=nullable, unique=unique)


def real(name: str, *, nullable: bool = False, unique: bool = False) -> Column:
    return Column(name=name, sql_type="REAL", nullable=nullable, unique=unique)


ADDRESS_COLUMNS = (
    text("{prefix}_line1"),
    text("{prefix}_line2", nullable=True),
    text("{prefix}_city"),
    text("{prefix}_region"),
    text("{prefix}_region_code"),
    text("{prefix}_postal_code"),
    text("{prefix}_country"),
    text("{prefix}_country_code"),
    real("{prefix}_latitude", nullable=True),
    real("{prefix}_longitude", nullable=True),
)


def address_columns(prefix: str) -> tuple[Column, ...]:
    return tuple(
        Column(
            name=column.name.format(prefix=prefix),
            sql_type=column.sql_type,
            nullable=column.nullable,
            unique=column.unique,
        )
        for column in ADDRESS_COLUMNS
    )


COMPANY_COLUMNS = (
    text("id"),
    text("name"),
    text("legal_entity_type"),
    integer("founded_year"),
    text("industry"),
    text("size_band"),
    integer("employee_count"),
    integer("revenue_min_usd"),
    integer("revenue_max_usd"),
    text("revenue_currency"),
    text("funding_stage"),
    *address_columns("headquarters"),
    text("incorporated_country"),
    text("incorporated_country_code"),
    text("incorporated_region"),
    text("incorporated_region_code"),
    text("domain", unique=True),
    text("website_url"),
    text("website_host"),
    text("email_pattern"),
    text("linkedin_slug"),
    text("departments_json"),
    text("leadership_json"),
)

PEOPLE_COLUMNS = (
    text("id"),
    text("company_id"),
    text("given_name"),
    text("family_name"),
    text("name"),
    text("username", unique=True),
    text("birthdate"),
    text("locale"),
    text("email", unique=True),
    text("phone_e164", unique=True),
    text("phone_national"),
    text("phone_country_code"),
    text("phone_country_calling_code"),
    *address_columns("address"),
    text("job_title"),
    text("job_industry"),
    text("job_department"),
    text("job_level"),
    text("job_company_id", nullable=True),
    text("avatar"),
    text("website_url"),
    text("website_host"),
    text("bio"),
)

PRODUCT_COLUMNS = (
    text("id"),
    text("company_id"),
    text("name"),
    text("slug", unique=True),
    text("product_type"),
    text("lifecycle_stage"),
    integer("launch_year"),
    text("industry"),
    text("category"),
    text("owner_department"),
    text("target_departments_json"),
    text("target_size_band"),
    text("description"),
    text("website_url"),
    text("website_host"),
    text("pricing_model"),
    text("features_json"),
)

PRODUCT_PLAN_COLUMNS = (
    text("product_id"),
    text("sku"),
    text("name"),
    text("description"),
    text("billing_interval"),
    integer("price_min_usd"),
    integer("price_max_usd"),
    text("price_currency"),
    text("included_features_json"),
)

SOCIAL_COLUMNS = (text("person_id"), text("platform"), text("handle"), text("url"))
METADATA_COLUMNS = (text("key"), text("value"))
COMPANY_WIDE_COLUMNS = (
    text("company_name"),
    text("company_industry"),
    text("company_size_band", nullable=True),
    integer("company_employee_count", nullable=True),
    text("company_domain"),
    text("company_website_url"),
    text("company_country_code", nullable=True),
    text("company_region_code", nullable=True),
)

RELATIONAL_SCHEMAS: tuple[TableSchema, ...] = (
    TableSchema(
        "companies",
        COMPANY_COLUMNS,
        primary_key=("id",),
        indexes=(("idx_companies_domain", ("domain",)),),
    ),
    TableSchema(
        "people",
        PEOPLE_COLUMNS,
        primary_key=("id",),
        foreign_keys=(ForeignKey("company_id", "companies"),),
        indexes=(
            ("idx_people_company_id", ("company_id",)),
            ("idx_people_email", ("email",)),
            ("idx_people_username", ("username",)),
        ),
    ),
    TableSchema(
        "products",
        PRODUCT_COLUMNS,
        primary_key=("id",),
        foreign_keys=(ForeignKey("company_id", "companies"),),
        indexes=(
            ("idx_products_company_id", ("company_id",)),
            ("idx_products_slug", ("slug",)),
        ),
    ),
    TableSchema(
        "product_plans",
        PRODUCT_PLAN_COLUMNS,
        primary_key=("product_id", "sku"),
        foreign_keys=(ForeignKey("product_id", "products", on_delete="CASCADE"),),
        indexes=(("idx_product_plans_product_id", ("product_id",)),),
    ),
    TableSchema(
        "social_accounts",
        SOCIAL_COLUMNS,
        primary_key=("person_id", "platform"),
        foreign_keys=(ForeignKey("person_id", "people", on_delete="CASCADE"),),
        indexes=(("idx_social_accounts_person_id", ("person_id",)),),
    ),
    TableSchema("export_metadata", METADATA_COLUMNS, primary_key=("key",)),
)

WIDE_SCHEMAS: tuple[TableSchema, ...] = (
    TableSchema(
        "people_wide",
        (*PEOPLE_COLUMNS, *COMPANY_WIDE_COLUMNS),
        primary_key=("id",),
        indexes=(("idx_people_wide_company_id", ("company_id",)),),
    ),
    TableSchema(
        "products_wide",
        (*PRODUCT_COLUMNS, *COMPANY_WIDE_COLUMNS),
        primary_key=("id",),
        indexes=(("idx_products_wide_company_id", ("company_id",)),),
    ),
)


def schemas_for_layout(layout: ExportLayout) -> tuple[TableSchema, ...]:
    if layout == "relational":
        return RELATIONAL_SCHEMAS
    if layout == "wide":
        return (*WIDE_SCHEMAS, RELATIONAL_SCHEMAS[-1])
    if layout == "both":
        return (*RELATIONAL_SCHEMAS[:-1], *WIDE_SCHEMAS, RELATIONAL_SCHEMAS[-1])
    raise ValueError(f"unsupported export layout {layout!r}")


def schema_by_name(layout: ExportLayout) -> dict[str, TableSchema]:
    return {schema.name: schema for schema in schemas_for_layout(layout)}
