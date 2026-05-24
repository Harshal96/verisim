from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from verisim.masking import (
    MaskingConfig,
    MaskingSession,
    mask_dataframe,
    mask_sql_table,
)


def test_detects_pii_columns_with_confidence_and_reasons():
    session = MaskingSession(MaskingConfig(seed=7))
    rows = [
        {
            "customer_name": "Alice Adams",
            "email_address": "alice@example.com",
            "mobile_phone": "(415) 555-0100",
            "shipping_address": "1 Main Street",
            "city": "San Francisco",
            "metadata": ["not", "pii"],
            "notes": "prefers email",
        }
    ]

    detected = {column.name: column for column in session.detect_columns(rows)}

    assert detected["customer_name"].kind == "name"
    assert detected["email_address"].kind == "email"
    assert detected["mobile_phone"].kind == "phone"
    assert detected["shipping_address"].kind == "address_line1"
    assert detected["city"].kind == "city"
    assert "metadata" not in detected
    assert "notes" not in detected
    assert detected["email_address"].confidence >= 0.65
    assert detected["email_address"].reasons


def test_mask_dataframe_preserves_entity_consistency_and_non_pii_values():
    original = pd.DataFrame(
        [
            {
                "customer_name": "Alice Adams",
                "email": "alice@company.com",
                "phone": "+1 415 555 0100",
                "address_line1": "1 Main Street",
                "city": "San Francisco",
                "amount": 19.95,
            },
            {
                "customer_name": "Alice Adams",
                "email": "alice@company.com",
                "phone": "+1 415 555 0100",
                "address_line1": "1 Main Street",
                "city": "San Francisco",
                "amount": 29.95,
            },
            {
                "customer_name": "Bob Brown",
                "email": "bob@company.com",
                "phone": "+1 212 555 0199",
                "address_line1": "9 Market Street",
                "city": "New York",
                "amount": 39.95,
            },
        ],
        index=["a1", "a2", "b1"],
    )

    result = mask_dataframe(original, config=MaskingConfig(seed=123))
    masked = result.data

    assert original.loc["a1", "email"] == "alice@company.com"
    assert list(masked.index) == ["a1", "a2", "b1"]
    assert masked["amount"].tolist() == [19.95, 29.95, 39.95]
    assert masked.loc["a1", "email"] == masked.loc["a2", "email"]
    assert masked.loc["a1", "customer_name"] == masked.loc["a2", "customer_name"]
    assert masked.loc["a1", "phone"] == masked.loc["a2", "phone"]
    assert masked.loc["a1", "email"] != "alice@company.com"
    assert masked.loc["b1", "email"] != masked.loc["a1", "email"]
    assert masked.loc["a1", "email"].endswith(".example.invalid")
    assert masked.loc["a1", "phone"].startswith("+")
    assert result.row_count == 3
    assert {column.kind for column in result.columns} >= {
        "name",
        "email",
        "phone",
        "address_line1",
        "city",
    }


def test_masking_session_preserves_mappings_across_dataframes():
    session = MaskingSession(MaskingConfig(seed=55))
    first = pd.DataFrame([{"name": "Alice Adams", "email": "alice@company.com"}])
    second = pd.DataFrame(
        [{"billing_name": "Alice Adams", "billing_email": "alice@company.com"}]
    )

    masked_first = session.mask_dataframe(first).data
    masked_second = session.mask_dataframe(second).data

    assert masked_first.loc[0, "email"] == masked_second.loc[0, "billing_email"]
    assert masked_first.loc[0, "name"] == masked_second.loc[0, "billing_name"]


def test_mask_rows_supports_explicit_identity_and_address_overrides():
    session = MaskingSession(
        MaskingConfig(
            seed=71,
            identity_columns=("customer_id",),
            column_overrides={
                "first": "given_name",
                "last": "family_name",
                "full_address": "address",
                "region_name": "region",
                "region_code": "region_code",
                "postal": "postal_code",
                "country_name": "country",
                "country_code": "country_code",
                "phone": "phone",
                "empty_email": "email",
            },
        )
    )
    rows = [
        {
            "customer_id": "cust-1",
            "first": "Alice",
            "last": "Adams",
            "full_address": "1 Main Street, Chicago, IL 60601",
            "region_name": "Illinois",
            "region_code": "IL",
            "postal": "60601",
            "country_name": "United States",
            "country_code": "US",
            "phone": "(415) 555-0100",
            "empty_email": "",
            "order_total": 25,
        },
        {
            "customer_id": "cust-1",
            "first": "Alice",
            "last": "Adams",
            "full_address": "1 Main Street, Chicago, IL 60601",
            "region_name": "Illinois",
            "region_code": "IL",
            "postal": "60601",
            "country_name": "United States",
            "country_code": "US",
            "phone": "(415) 555-0100",
            "empty_email": "",
            "order_total": 30,
        },
    ]

    masked = session.mask_rows(rows)

    assert masked.rows[0]["first"] == masked.rows[1]["first"]
    assert masked.rows[0]["last"] == masked.rows[1]["last"]
    assert masked.rows[0]["full_address"] == masked.rows[1]["full_address"]
    assert masked.rows[0]["phone"] == masked.rows[1]["phone"]
    assert masked.rows[0]["phone"].startswith("(")
    assert masked.rows[0]["first"] != "Alice"
    assert masked.rows[0]["last"] != "Adams"
    assert masked.rows[0]["region_name"] != "Illinois"
    assert len(str(masked.rows[0]["region_code"])) == 2
    assert len(str(masked.rows[0]["country_code"])) == 2
    assert masked.rows[0]["empty_email"] == ""
    assert masked.rows[0]["order_total"] == 25


def test_explicit_identity_columns_must_exist():
    session = MaskingSession(MaskingConfig(identity_columns=("customer_id",)))

    with pytest.raises(ValueError, match="identity columns are missing"):
        session.mask_rows([{"email": "alice@example.com"}])


def test_mask_dataframe_rejects_non_dataframe_inputs():
    session = MaskingSession()

    with pytest.raises(TypeError, match="pandas DataFrame"):
        session.mask_dataframe([{"email": "alice@example.com"}])


def test_mask_sql_table_creates_masked_copy_without_mutating_source():
    connection = sqlite3.connect(":memory:")
    connection.execute("""
        CREATE TABLE patients (
            id INTEGER PRIMARY KEY,
            patient_name TEXT,
            email TEXT,
            phone TEXT,
            city TEXT,
            diagnosis TEXT
        )
        """)
    connection.executemany(
        """
        INSERT INTO patients (patient_name, email, phone, city, diagnosis)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                "Alice Adams",
                "alice@hospital.example",
                "+1 415 555 0100",
                "San Francisco",
                "routine",
            ),
            (
                "Alice Adams",
                "alice@hospital.example",
                "+1 415 555 0100",
                "San Francisco",
                "followup",
            ),
            (
                "Bob Brown",
                "bob@hospital.example",
                "+1 212 555 0199",
                "New York",
                "routine",
            ),
        ],
    )

    result = mask_sql_table(
        connection,
        "patients",
        "patients_masked",
        config=MaskingConfig(seed=90),
    )
    source_rows = connection.execute(
        "SELECT patient_name, email, diagnosis FROM patients ORDER BY id"
    ).fetchall()
    masked_rows = connection.execute(
        "SELECT patient_name, email, phone, city, diagnosis FROM patients_masked "
        "ORDER BY id"
    ).fetchall()

    assert source_rows[0] == ("Alice Adams", "alice@hospital.example", "routine")
    assert masked_rows[0][1] == masked_rows[1][1]
    assert masked_rows[0][0] == masked_rows[1][0]
    assert masked_rows[0][2] == masked_rows[1][2]
    assert masked_rows[0][1] != "alice@hospital.example"
    assert masked_rows[2][1] != masked_rows[0][1]
    assert [row[4] for row in masked_rows] == ["routine", "followup", "routine"]
    assert result.destination_table == "patients_masked"
    assert result.row_count == 3


def test_mask_sql_table_rejects_unsafe_identifiers():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE patients (email TEXT)")

    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        mask_sql_table(connection, "patients; DROP TABLE patients", "masked")


def test_masking_session_preserves_mappings_across_sql_tables():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE contacts (id INTEGER, email TEXT, name TEXT)")
    connection.execute("CREATE TABLE invoices (id INTEGER, email TEXT, total INTEGER)")
    connection.execute(
        "INSERT INTO contacts (id, email, name) VALUES (?, ?, ?)",
        (1, "alice@company.com", "Alice Adams"),
    )
    connection.execute(
        "INSERT INTO invoices (id, email, total) VALUES (?, ?, ?)",
        (10, "alice@company.com", 125),
    )
    session = MaskingSession(MaskingConfig(seed=91))

    session.mask_sql_table(connection, "contacts", "contacts_masked")
    session.mask_sql_table(connection, "invoices", "invoices_masked")

    contact_email = connection.execute("SELECT email FROM contacts_masked").fetchone()[
        0
    ]
    invoice_email = connection.execute("SELECT email FROM invoices_masked").fetchone()[
        0
    ]
    invoice_total = connection.execute("SELECT total FROM invoices_masked").fetchone()[
        0
    ]

    assert contact_email == invoice_email
    assert contact_email != "alice@company.com"
    assert invoice_total == 125
