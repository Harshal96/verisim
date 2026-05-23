from __future__ import annotations

import json
import sqlite3
from csv import DictReader

import click
from typer.testing import CliRunner

import verisim.cli as cli
from verisim.cli import app

runner = CliRunner()


def _plain_output(result) -> str:
    return click.unstyle(result.output)


def test_cli_version_option():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("verisim ")


def test_cli_generates_person_record_json():
    result = runner.invoke(app, ["person-record", "--seed", "123"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["person"]["name"]
    assert payload["contact"]["email"].endswith(".example.invalid")


def test_cli_repeat_outputs_one_json_record_per_separator():
    result = runner.invoke(app, ["person-record", "--seed", "123", "-r", "2"])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line]
    assert len(lines) == 2
    assert all(json.loads(line)["person"]["name"] for line in lines)


def test_cli_locale_seed_and_output_file(tmp_path):
    output = tmp_path / "person.jsonl"

    result = runner.invoke(
        app,
        [
            "person-record",
            "--locale",
            "en_IN",
            "--script",
            "latin",
            "--seed",
            "13",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    payload = json.loads(output.read_text())
    assert payload["address"]["country_code"] == "IN"
    assert payload["person"]["name"].isascii()


def test_cli_dataset_generates_people_and_companies():
    result = runner.invoke(
        app,
        ["dataset", "--people", "4", "--companies", "2", "--seed", "123"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["people"]) == 4
    assert len(payload["companies"]) == 2


def test_cli_dataset_exports_csv_directory_with_wide_layout(tmp_path):
    output = tmp_path / "tables"

    result = runner.invoke(
        app,
        [
            "dataset",
            "--people",
            "3",
            "--companies",
            "2",
            "--products",
            "1",
            "--seed",
            "123",
            "--format",
            "csv",
            "--layout",
            "both",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert (output / "companies.csv").exists()
    assert (output / "people.csv").exists()
    assert (output / "people_wide.csv").exists()
    assert (output / "products_wide.csv").exists()


def test_cli_dataset_exports_sqlite_database(tmp_path):
    output = tmp_path / "dataset.sqlite"

    result = runner.invoke(
        app,
        [
            "dataset",
            "--people",
            "3",
            "--companies",
            "2",
            "--products",
            "1",
            "--seed",
            "123",
            "--format",
            "sqlite",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    with sqlite3.connect(output) as connection:
        people_count = connection.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        company_count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[
            0
        ]
        metadata = dict(connection.execute("SELECT key, value FROM export_metadata"))
    assert people_count == 3
    assert company_count == 2
    assert metadata["locale"] == "en_US"
    assert metadata["seed"] == "123"


def test_cli_dataset_exports_sql_dump(tmp_path):
    output = tmp_path / "dataset.sql"

    result = runner.invoke(
        app,
        [
            "dataset",
            "--people",
            "1",
            "--companies",
            "1",
            "--seed",
            "123",
            "--format",
            "sql",
            "--sql-mode",
            "insert",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "CREATE TABLE companies" in output.read_text()
    assert "INSERT INTO people" in output.read_text()


def test_cli_dataset_requires_output_for_file_based_formats():
    result = runner.invoke(app, ["dataset", "--format", "csv"])

    assert result.exit_code != 0
    assert "--output is required when --format is not json" in _plain_output(result)


def test_cli_record_command_exports_repeated_records_as_csv(tmp_path):
    output = tmp_path / "people.csv"

    result = runner.invoke(
        app,
        [
            "person-record",
            "--repeat",
            "3",
            "--seed",
            "123",
            "--format",
            "csv",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(DictReader(stream))
    assert len(rows) == 3
    assert rows[0]["person_name"]


def test_cli_generates_product_record_json():
    result = runner.invoke(app, ["product-record", "--seed", "123"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["name"]
    assert payload["company"]["domain"].endswith(".example.invalid")
    assert payload["website"]["url"].endswith(f"/products/{payload['slug']}")
    assert payload["plans"]


def test_cli_generates_new_domain_record_json():
    targets = {
        "order-record": "line_items",
        "transaction-record": "amount_minor",
        "event-record": "participants",
        "support-ticket-record": "assigned_agent",
        "review-record": "rating",
        "medical-record": "diagnoses",
    }

    for target, expected_key in targets.items():
        result = runner.invoke(app, [target, "--seed", "123"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload[expected_key]


def test_cli_rejects_unknown_target_with_supported_choices():
    result = runner.invoke(app, ["unknown"])
    output = _plain_output(result)

    assert result.exit_code != 0
    assert "unsupported target" in output
    assert "person-record" in output


def test_cli_rejects_unknown_option():
    result = runner.invoke(app, ["--bogus"])

    assert result.exit_code != 0
    assert "No such option" in _plain_output(result)


def test_cli_version_falls_back_when_package_metadata_is_missing(monkeypatch):
    def missing_version(_: str) -> str:
        raise cli.PackageNotFoundError

    monkeypatch.setattr(cli, "version", missing_version)

    assert cli._package_version() == "0.0.0"


def test_cli_main_invokes_typer_app(monkeypatch):
    called = False

    def fake_app() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "app", fake_app)

    cli.main()

    assert called is True
