from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from verisim.fixtures.config import load_config
from verisim.fixtures.sources import FixtureSourceError, load_sources


class Payload(BaseModel):
    name: str


class NestedPayload(BaseModel):
    payload: Payload


def _config(
    tmp_path: Path,
    document: dict[str, object],
    operations: dict[str, object],
    *,
    pydantic: bool = False,
):
    api = tmp_path / "openapi.json"
    api.write_text(json.dumps(document), encoding="utf-8")
    payload = {
        "version": 1,
        "project": {"root": str(tmp_path), "revision": "rev-1"},
        "sources": {
            "openapi": {"files": ["openapi.json"]},
            **(
                {"pydantic": {"models": {"payload": f"{__name__}:Payload"}}}
                if pydantic
                else {}
            ),
        },
        "operations": operations,
        "branches": {"adapter": "tests:catalog"},
        "execution": {"runner": "tests:runner"},
        "generation": {"clock": "2026-01-01T00:00:00Z", "candidate_limit": 20},
        "minimization": {
            "unit": "scenario",
            "method": "exact_set_cover",
            "require_full_coverage": True,
            "timeout_seconds": 1,
        },
        "output": {"format": "json", "path": "out.json", "report": "report.json"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_config(path, environ={})


def test_loads_openapi3_and_resolves_local_schema_refs(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        {
            "openapi": "3.1.0",
            "paths": {
                "/orders/{order_id}": {
                    "post": {
                        "operationId": "createOrder",
                        "parameters": [
                            {
                                "name": "order_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer", "minimum": 1},
                            }
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"}
                                }
                            },
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "Order": {
                        "type": "object",
                        "required": ["sku"],
                        "properties": {
                            "sku": {"type": "string", "enum": ["a", "b"]},
                            "quantity": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                            },
                        },
                    }
                }
            },
        },
        {"createOrder": {}},
    )

    sources = load_sources(config)
    operation = sources.operations["createOrder"]
    assert operation.method == "POST"
    assert operation.path == "/orders/{order_id}"
    assert operation.request_schema["properties"]["sku"]["enum"] == ["a", "b"]
    assert operation.parameters[0]["in"] == "path"
    assert sources.input_fingerprint.startswith("sha256:")


def test_loads_swagger2_body_parameters(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        {
            "swagger": "2.0",
            "consumes": ["application/json"],
            "paths": {
                "/pets": {
                    "post": {
                        "operationId": "createPet",
                        "parameters": [
                            {
                                "name": "body",
                                "in": "body",
                                "required": True,
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                },
                            }
                        ],
                    }
                }
            },
        },
        {"createPet": {}},
    )
    operation = load_sources(config).operations["createPet"]
    assert operation.request_schema["properties"]["name"]["type"] == "string"


def test_resolves_nested_pydantic_model_refs(tmp_path: Path) -> None:
    from verisim.fixtures.sources import _SchemaResolver

    schema = NestedPayload.model_json_schema()
    resolved = _SchemaResolver(schema, Path("nested-model")).resolve(schema)
    assert resolved["properties"]["payload"]["properties"]["name"]["type"] == "string"


def test_rejects_duplicate_operation_ids_and_remote_refs(tmp_path: Path) -> None:
    duplicate = _config(
        tmp_path,
        {
            "openapi": "3.0.0",
            "paths": {
                "/a": {"get": {"operationId": "same"}},
                "/b": {"get": {"operationId": "same"}},
            },
        },
        {"same": {}},
    )
    with pytest.raises(FixtureSourceError, match="duplicate operationId"):
        load_sources(duplicate)

    remote = _config(
        tmp_path,
        {
            "openapi": "3.0.0",
            "paths": {
                "/a": {
                    "post": {
                        "operationId": "create",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "https://example.invalid/schema"}
                                }
                            }
                        },
                    }
                }
            },
        },
        {"create": {}},
    )
    with pytest.raises(FixtureSourceError, match="remote"):
        load_sources(remote)


def test_rejects_unresolved_refs_and_unsupported_schema_keywords(
    tmp_path: Path,
) -> None:
    unresolved = _config(
        tmp_path,
        {
            "openapi": "3.0.0",
            "paths": {
                "/create": {
                    "post": {
                        "operationId": "create",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Missing"}
                                }
                            }
                        },
                    }
                }
            },
        },
        {"create": {}},
    )
    with pytest.raises(FixtureSourceError, match="unresolved"):
        load_sources(unresolved)

    unsupported = _config(
        tmp_path,
        {
            "openapi": "3.0.0",
            "paths": {
                "/create": {
                    "post": {
                        "operationId": "create",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "string",
                                        "pattern": "^[a-z]+$",
                                    }
                                }
                            }
                        },
                    }
                }
            },
        },
        {"create": {}},
    )
    with pytest.raises(FixtureSourceError, match="unsupported schema"):
        load_sources(unsupported)


def test_imports_pydantic_models_and_checks_missing_configured_operations(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        {
            "openapi": "3.0.0",
            "paths": {
                "/pets": {
                    "post": {
                        "operationId": "createPet",
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"type": "object"}}
                            }
                        },
                    }
                }
            },
        },
        {"createPet": {"request_model": "payload"}},
        pydantic=True,
    )
    sources = load_sources(config)
    assert sources.model_classes["payload"] is Payload

    missing = _config(tmp_path, {"openapi": "3.0.0", "paths": {}}, {"missing": {}})
    with pytest.raises(FixtureSourceError, match="not found"):
        load_sources(missing)
