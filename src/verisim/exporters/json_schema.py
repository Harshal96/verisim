from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

SchemaDialect = Literal["json-schema-2020-12", "openapi-3.1"]


def export_json_schema(
    model: type[BaseModel],
    *,
    dialect: SchemaDialect = "json-schema-2020-12",
    title: str | None = None,
    ref_template: str = "#/$defs/{model}",
) -> dict[str, object]:
    schema = dict(model.model_json_schema(ref_template=ref_template))
    if title is not None:
        schema["title"] = title
    if dialect == "json-schema-2020-12":
        schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    elif dialect == "openapi-3.1":
        schema.pop("$schema", None)
    else:
        raise ValueError(f"unsupported schema dialect {dialect!r}")
    return schema


def export_openapi_components(
    models: Iterable[type[BaseModel]],
    *,
    title: str = "Verisim synthetic data contract",
    version: str = "1.0.0",
) -> dict[str, object]:
    schemas = {
        model.__name__: export_json_schema(model, dialect="openapi-3.1")
        for model in models
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": {},
        "components": {"schemas": schemas},
    }


def write_json_schema(
    model: type[BaseModel],
    output: str | Path,
    *,
    dialect: SchemaDialect = "json-schema-2020-12",
    title: str | None = None,
) -> None:
    payload = export_json_schema(model, dialect=dialect, title=title)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )


def write_openapi_components(
    models: Iterable[type[BaseModel]],
    output: str | Path,
    *,
    title: str = "Verisim synthetic data contract",
    version: str = "1.0.0",
) -> None:
    payload = export_openapi_components(models, title=title, version=version)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )


__all__ = [
    "SchemaDialect",
    "export_json_schema",
    "export_openapi_components",
    "write_json_schema",
    "write_openapi_components",
]
