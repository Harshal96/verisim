from __future__ import annotations

import json
import sqlite3
from importlib.util import find_spec
from csv import DictReader
from itertools import islice

import pytest

from verisim import DatasetEvent, DatasetSpec, PersonRecord, Verisim
from verisim.exporters import export_dataset, export_records


def test_export_dataset_is_available_from_package_root():
    from verisim import export_dataset as root_export_dataset

    assert root_export_dataset is export_dataset


def test_export_dataset_writes_nested_json(tmp_path):
    dataset = Verisim(locale="en_US", seed=7).dataset(
        DatasetSpec(people=2, companies=1, products=1)
    )
    output = tmp_path / "dataset.json"

    export_dataset(dataset, "json", output)

    payload = json.loads(output.read_text())
    assert len(payload["people"]) == 2
    assert len(payload["companies"]) == 1
    assert len(payload["products"]) == 1
    assert payload["people"][0]["company"]["id"] == payload["companies"][0]["id"]


def test_export_dataset_rejects_unknown_format(tmp_path):
    dataset = Verisim(locale="en_US", seed=7).dataset(
        DatasetSpec(people=0, companies=0)
    )

    with pytest.raises(ValueError, match="unsupported export format"):
        export_dataset(dataset, "yaml", tmp_path / "dataset.yaml")


def test_export_dataset_writes_relational_csv_tables(tmp_path):
    dataset = Verisim(locale="en_US", seed=8).dataset(
        DatasetSpec(people=3, companies=2, products=2)
    )
    output = tmp_path / "tables"

    export_dataset(dataset, "csv", output)

    companies = _read_csv(output / "companies.csv")
    people = _read_csv(output / "people.csv")
    products = _read_csv(output / "products.csv")
    product_plans = _read_csv(output / "product_plans.csv")
    social_accounts = _read_csv(output / "social_accounts.csv")
    metadata = _read_csv(output / "export_metadata.csv")
    company_ids = {company["id"] for company in companies}

    assert len(companies) == 2
    assert len(people) == 3
    assert len(products) == 2
    assert len(product_plans) == sum(len(product.plans) for product in dataset.products)
    assert len(social_accounts) == 12
    assert metadata == [
        {"key": "schema_version", "value": "1"},
        {"key": "people_count", "value": "3"},
        {"key": "companies_count", "value": "2"},
        {"key": "products_count", "value": "2"},
    ]
    assert all(person["company_id"] in company_ids for person in people)
    assert all(product["company_id"] in company_ids for product in products)
    assert people[0]["email"].endswith(".example.invalid")
    assert products[0]["website_url"].endswith(f"/products/{products[0]['slug']}")


def test_iter_dataset_stream_matches_materialized_dataset_order():
    spec = DatasetSpec(people=4, companies=2, products=3)

    streamed = list(Verisim(locale="en_US", seed=12).iter_dataset(spec))
    materialized = Verisim(locale="en_US", seed=12).dataset(spec)

    assert [event.kind for event in streamed] == [
        "company",
        "company",
        "person",
        "person",
        "person",
        "person",
        "product",
        "product",
        "product",
    ]
    assert [event.record for event in streamed[:2]] == materialized.companies
    assert [event.record for event in streamed[2:6]] == materialized.people
    assert [event.record for event in streamed[6:]] == materialized.products
    assert all(isinstance(event, DatasetEvent) for event in streamed)


def test_export_dataset_accepts_streamed_events_and_writes_wide_csv_tables(tmp_path):
    spec = DatasetSpec(people=3, companies=2, products=2)
    stream = Verisim(locale="en_US", seed=18).iter_dataset(spec)
    output = tmp_path / "tables"

    export_dataset(stream, "csv", output, layout="both", batch_size=2)

    people = _read_csv(output / "people.csv")
    people_wide = _read_csv(output / "people_wide.csv")
    products_wide = _read_csv(output / "products_wide.csv")
    metadata = _read_csv(output / "export_metadata.csv")

    assert len(people) == 3
    assert len(people_wide) == 3
    assert len(products_wide) == 2
    assert people_wide[0]["company_name"]
    assert people_wide[0]["company_domain"].endswith(".example.invalid")
    assert products_wide[0]["company_name"]
    assert metadata[:4] == [
        {"key": "schema_version", "value": "1"},
        {"key": "people_count", "value": "3"},
        {"key": "companies_count", "value": "2"},
        {"key": "products_count", "value": "2"},
    ]


def test_export_dataset_writes_stable_csv_headers_for_empty_tables(tmp_path):
    dataset = Verisim(locale="en_US", seed=10).dataset(
        DatasetSpec(people=0, companies=1, products=0)
    )
    output = tmp_path / "tables"

    export_dataset(dataset, "csv", output)

    product_header = (output / "products.csv").read_text().splitlines()[0]
    product_plan_header = (output / "product_plans.csv").read_text().splitlines()[0]
    social_header = (output / "social_accounts.csv").read_text().splitlines()[0]
    assert product_header.startswith("id,company_id,name,slug")
    assert product_plan_header.startswith("product_id,sku,name")
    assert social_header == "person_id,platform,handle,url"


def test_export_dataset_writes_postgres_copy_sql_dump(tmp_path):
    dataset = Verisim(locale="en_US", seed=20).dataset(
        DatasetSpec(people=2, companies=1, products=1)
    )
    output = tmp_path / "dataset.sql"

    export_dataset(dataset, "sql", output, sql_mode="copy", layout="relational")

    dump = output.read_text()
    assert "CREATE TABLE companies" in dump
    assert "company_id TEXT NOT NULL REFERENCES companies(id)" in dump
    assert "COPY companies (" in dump
    assert "COPY people (" in dump
    assert "\\." in dump
    assert "INSERT INTO" not in dump


def test_export_dataset_writes_insert_sql_dump_with_escaping(tmp_path):
    dataset = Verisim(locale="en_US", seed=21).dataset(
        DatasetSpec(people=1, companies=1, products=0)
    )
    dataset.companies[0].name = "O'Hara Analytics"
    output = tmp_path / "dataset.sql"

    export_dataset(dataset, "sql", output, sql_mode="insert", layout="wide")

    dump = output.read_text()
    assert "CREATE TABLE people_wide" in dump
    assert "INSERT INTO people_wide" in dump
    assert "O''Hara Analytics" in dump
    assert "COPY " not in dump


def test_export_dataset_writes_indexed_sqlite_database(tmp_path):
    dataset = Verisim(locale="en_US", seed=9).dataset(
        DatasetSpec(people=4, companies=2, products=3)
    )
    output = tmp_path / "dataset.sqlite"

    export_dataset(dataset, "sqlite", output)

    connection = sqlite3.connect(output)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    assert _table_count(connection, "companies") == 2
    assert _table_count(connection, "people") == 4
    assert _table_count(connection, "products") == 3
    assert _table_count(connection, "product_plans") == sum(
        len(product.plans) for product in dataset.products
    )
    assert _table_count(connection, "social_accounts") == 16
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert _foreign_tables(connection, "people") == {"companies"}
    assert _foreign_tables(connection, "products") == {"companies"}
    assert _foreign_tables(connection, "product_plans") == {"products"}
    assert _foreign_tables(connection, "social_accounts") == {"people"}
    assert {
        row["name"] for row in connection.execute("PRAGMA index_list('people')")
    } >= {"idx_people_company_id", "idx_people_email", "idx_people_username"}
    assert {
        row["name"] for row in connection.execute("PRAGMA index_list('products')")
    } >= {"idx_products_company_id", "idx_products_slug"}
    metadata = dict(connection.execute("SELECT key, value FROM export_metadata"))
    assert metadata["schema_version"] == "1"
    assert metadata["people_count"] == "4"


def test_export_dataset_overwrites_existing_sqlite_database(tmp_path):
    dataset = Verisim(locale="en_US", seed=11).dataset(
        DatasetSpec(people=0, companies=1, products=0)
    )
    output = tmp_path / "dataset.sqlite"
    output.write_text("stale")

    export_dataset(dataset, "sqlite", output)

    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0


def test_export_records_writes_repeated_records_as_one_csv_file(tmp_path):
    verisim = Verisim(locale="en_US", seed=30)
    records = verisim.iter_records(PersonRecord, count=3)
    output = tmp_path / "people.csv"

    export_records(records, PersonRecord, "csv", output, batch_size=2)

    rows = _read_csv(output)
    assert len(rows) == 3
    assert rows[0]["person_name"]
    assert rows[0]["contact_email"].endswith(".example.invalid")
    assert "company_name" in rows[0]


def test_export_records_writes_jsonl_without_materializing(tmp_path):
    verisim = Verisim(locale="en_US", seed=31)
    records = verisim.iter_records(PersonRecord)
    output = tmp_path / "people.jsonl"

    export_records(islice(records, 2), PersonRecord, "jsonl", output)

    lines = output.read_text().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["person"]["name"] for line in lines)


def test_binary_export_formats_explain_optional_dependencies(tmp_path):
    if find_spec("pyarrow") is not None or find_spec("fastavro") is not None:
        pytest.skip("base-install missing dependency behavior only")
    dataset = Verisim(locale="en_US", seed=32).dataset(
        DatasetSpec(people=1, companies=1, products=0)
    )

    with pytest.raises(ImportError, match="verisim\\[export\\]"):
        export_dataset(dataset, "parquet", tmp_path / "parquet")

    with pytest.raises(ImportError, match="verisim\\[export\\]"):
        export_dataset(dataset, "avro", tmp_path / "avro")


def test_pyarrow_export_formats_round_trip_when_extra_is_installed(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    dataset = Verisim(locale="en_US", seed=33).dataset(
        DatasetSpec(people=2, companies=1, products=1)
    )

    parquet_output = tmp_path / "parquet"
    feather_output = tmp_path / "feather"
    arrow_output = tmp_path / "arrow"
    export_dataset(dataset, "parquet", parquet_output, layout="both", batch_size=1)
    export_dataset(dataset, "feather", feather_output, layout="relational")
    export_dataset(dataset, "arrow", arrow_output, layout="relational")

    assert pq.read_table(parquet_output / "people.parquet").num_rows == 2
    assert pq.read_table(parquet_output / "people_wide.parquet").num_rows == 2
    with pa.ipc.open_file(feather_output / "companies.feather") as reader:
        assert reader.read_all().num_rows == 1
    with pa.ipc.open_stream(arrow_output / "products.arrow") as reader:
        assert reader.read_all().num_rows == 1


def test_avro_export_round_trips_when_extra_is_installed(tmp_path):
    fastavro = pytest.importorskip("fastavro")
    dataset = Verisim(locale="en_US", seed=34).dataset(
        DatasetSpec(people=2, companies=1, products=0)
    )
    output = tmp_path / "avro"

    export_dataset(dataset, "avro", output, batch_size=1)

    with (output / "people.avro").open("rb") as stream:
        rows = list(fastavro.reader(stream))
    assert len(rows) == 2
    assert rows[0]["email"].endswith(".example.invalid")


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(DictReader(stream))


def _table_count(connection, table):
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _foreign_tables(connection, table):
    return {
        row["table"]
        for row in connection.execute(f"PRAGMA foreign_key_list('{table}')")
    }
