from __future__ import annotations

import json

from typer.testing import CliRunner

import verisim.cli as cli
from verisim.cli import app

runner = CliRunner()


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


def test_cli_rejects_unknown_target_with_supported_choices():
    result = runner.invoke(app, ["unknown"])

    assert result.exit_code != 0
    assert "unsupported target" in result.output
    assert "person-record" in result.output


def test_cli_rejects_unknown_option():
    result = runner.invoke(app, ["--bogus"])

    assert result.exit_code != 0
    assert "No such option" in result.output


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
