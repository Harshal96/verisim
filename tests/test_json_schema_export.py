from __future__ import annotations

import json

from pydantic import BaseModel
from typer.testing import CliRunner

from verisim import PersonRecord, export_json_schema, export_openapi_components
from verisim.cli import app


class ContractRecord(BaseModel):
    email: str
    company_name: str


def test_export_json_schema_for_verisim_model():
    schema = export_json_schema(PersonRecord)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "PersonRecord"
    assert "person" in schema["properties"]
    assert "$defs" in schema


def test_export_json_schema_for_custom_pydantic_model():
    schema = export_json_schema(ContractRecord)

    assert schema["title"] == "ContractRecord"
    assert set(schema["required"]) == {"email", "company_name"}
    assert schema["properties"]["email"]["type"] == "string"


def test_export_openapi_components_for_models():
    document = export_openapi_components([PersonRecord, ContractRecord])

    assert document["openapi"] == "3.1.0"
    assert document["paths"] == {}
    assert "PersonRecord" in document["components"]["schemas"]
    assert "ContractRecord" in document["components"]["schemas"]


def test_cli_schema_command_writes_json_schema(tmp_path):
    output = tmp_path / "person.schema.json"
    result = CliRunner().invoke(
        app,
        ["schema", "person-record", "--output", str(output)],
    )

    assert result.exit_code == 0
    payload = json.loads(output.read_text())
    assert payload["title"] == "PersonRecord"
    assert "person" in payload["properties"]


def test_cli_schema_command_writes_openapi_document(tmp_path):
    output = tmp_path / "openapi.json"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "person-record",
            "--dialect",
            "openapi-3.1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output.read_text())
    assert payload["openapi"] == "3.1.0"
    assert "PersonRecord" in payload["components"]["schemas"]
