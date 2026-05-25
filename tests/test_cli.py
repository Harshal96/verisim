from __future__ import annotations

import json
import sqlite3
from csv import DictReader
from datetime import UTC, datetime

import click
import pytest
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


@pytest.mark.parametrize(
    ("command", "payload_key"),
    (
        ("instruction-pairs", "examples"),
        ("classification", "examples"),
        ("ner", "sequences"),
        ("chat", "transcripts"),
    ),
)
def test_cli_ai_commands_emit_materialized_json(command: str, payload_key: str):
    result = runner.invoke(app, ["ai", command, "--count", "2", "--seed", "123"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload[payload_key]) == 2


@pytest.mark.parametrize(
    "command", ("instruction-pairs", "classification", "ner", "chat")
)
def test_cli_ai_commands_emit_jsonl_records(command: str):
    result = runner.invoke(
        app,
        ["ai", command, "--count", "2", "--seed", "123", "--format", "jsonl"],
    )

    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(lines) == 2


def test_cli_ai_classification_accepts_weighted_labels():
    result = runner.invoke(
        app,
        [
            "ai",
            "classification",
            "--count",
            "5",
            "--seed",
            "123",
            "--label",
            "positive=4",
            "--label",
            "critical=1",
        ],
    )

    assert result.exit_code == 0
    labels = [example["label"] for example in json.loads(result.stdout)["examples"]]
    assert labels.count("positive") == 4
    assert labels.count("critical") == 1


@pytest.mark.parametrize(
    ("label", "message"),
    (
        ("positive", "--label must use label=weight"),
        ("=1", "--label names must not be blank"),
        ("positive=many", "--label weights must be numeric"),
        ("positive=0", "--label weights must be positive"),
    ),
)
def test_cli_ai_classification_rejects_invalid_label_weights(label: str, message: str):
    result = runner.invoke(
        app,
        ["ai", "classification", "--label", label],
    )

    assert result.exit_code != 0
    assert message in _plain_output(result)


def test_cli_ai_chat_writes_jsonl_file(tmp_path):
    output = tmp_path / "chat.jsonl"

    result = runner.invoke(
        app,
        [
            "ai",
            "chat",
            "--count",
            "1",
            "--seed",
            "123",
            "--format",
            "jsonl",
            "--min-turns",
            "2",
            "--max-turns",
            "2",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    payload = json.loads(output.read_text())
    assert [message["role"] for message in payload["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_cli_activity_stream_outputs_seeded_jsonl():
    args = [
        "activity-stream",
        "--people",
        "1",
        "--events-per-person",
        "2",
        "--seed",
        "123",
        "--start-at",
        "2026-05-04T00:00:00+00:00",
        "--end-at",
        "2026-05-08T23:59:00+00:00",
    ]

    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0
    assert first.stdout == second.stdout
    lines = [json.loads(line) for line in first.stdout.splitlines()]
    assert len(lines) == 2
    assert all(line["schema_version"] == "1" for line in lines)
    assert [line["occurred_at"] for line in lines] == sorted(
        line["occurred_at"] for line in lines
    )


def test_cli_activity_stream_writes_jsonl_file(tmp_path):
    output = tmp_path / "events.jsonl"

    result = runner.invoke(
        app,
        [
            "activity-stream",
            "--people",
            "1",
            "--events-per-person",
            "2",
            "--seed",
            "123",
            "--output",
            str(output),
            "--start-at",
            datetime(2026, 5, 4, tzinfo=UTC).isoformat(),
            "--end-at",
            datetime(2026, 5, 8, 23, 59, tzinfo=UTC).isoformat(),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert len(output.read_text().splitlines()) == 2


def test_cli_activity_stream_requires_kafka_connection_options():
    result = runner.invoke(app, ["activity-stream", "--sink", "kafka"])

    assert result.exit_code != 0
    output = _plain_output(result)
    assert "--bootstrap-servers is required" in output
    assert "--topic is required" in output


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


def test_cli_record_edge_case_mode_outputs_boundary_json():
    result = runner.invoke(
        app,
        [
            "person-record",
            "--seed",
            "123",
            "--mode",
            "edge_cases",
            "--edge-case",
            "nul",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "\x00" in payload["bio"]


def test_cli_record_schema_violation_mode_raises_validation_error():
    result = runner.invoke(
        app,
        [
            "person-record",
            "--seed",
            "123",
            "--mode",
            "schema_violations",
            "--violation",
            "contact.email",
        ],
    )

    assert result.exit_code == 1
    assert result.exception is not None


def test_cli_record_duplicate_percent_keeps_requested_repeat_count():
    result = runner.invoke(
        app,
        [
            "person-record",
            "--seed",
            "123",
            "--repeat",
            "5",
            "--duplicate-percent",
            "40",
        ],
    )

    assert result.exit_code == 0
    payloads = [json.loads(line) for line in result.stdout.splitlines() if line]
    assert len(payloads) == 5
    assert len({payload["id"] for payload in payloads}) == 3


def test_cli_dataset_per_collection_duplicate_flags():
    result = runner.invoke(
        app,
        [
            "dataset",
            "--people",
            "5",
            "--companies",
            "4",
            "--products",
            "4",
            "--seed",
            "123",
            "--people-duplicate-percent",
            "40",
            "--companies-duplicate-percent",
            "25",
            "--products-duplicate-percent",
            "50",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["people"]) == 5
    assert len(payload["companies"]) == 4
    assert len(payload["products"]) == 4
    assert len({record["id"] for record in payload["people"]}) == 3
    assert len({record["id"] for record in payload["companies"]}) == 3
    assert len({record["id"] for record in payload["products"]}) == 2


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
