from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

from verisim.fixtures.schema import intersect
from verisim.fixtures.types import FixtureConfig


class FixtureSourceError(ValueError):
    """An API or model source cannot be normalized safely."""


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    method: str
    path: str
    parameters: tuple[dict[str, Any], ...]
    request_schema: dict[str, Any] | None
    request_content_type: str | None
    request_required: bool


@dataclass(frozen=True)
class LoadedSources:
    operations: dict[str, OperationContract]
    model_classes: dict[str, type[Any]]
    model_schemas: dict[str, dict[str, Any]]
    input_fingerprint: str
    files: tuple[Path, ...]


@contextmanager
def _python_paths(paths: list[Path]) -> Iterator[None]:
    additions = [str(path) for path in paths if str(path) not in sys.path]
    sys.path[:0] = additions
    try:
        yield
    finally:
        for path in additions:
            if path in sys.path:
                sys.path.remove(path)


def _import_reference(reference: str) -> Any:
    module_name, attribute = reference.split(":", 1)
    try:
        value: Any = importlib.import_module(module_name)
        for component in attribute.split("."):
            value = getattr(value, component)
        return value
    except (ImportError, AttributeError) as error:
        raise FixtureSourceError(
            f"could not import configured model {reference!r}: {error}"
        ) from error


def load_sources(
    config: FixtureConfig,
    *,
    model_overrides: dict[str, type[Any]] | None = None,
) -> LoadedSources:
    """Load configured OpenAPI documents and model classes deterministically."""
    model_overrides = model_overrides or {}
    operations: dict[str, OperationContract] = {}
    digests: list[tuple[str, str]] = []
    files = tuple(config.sources.openapi.files)
    for file_path in files:
        try:
            raw_bytes = file_path.read_bytes()
        except OSError as error:
            raise FixtureSourceError(
                f"cannot read OpenAPI file {file_path}: {error}"
            ) from error
        digests.append((str(file_path), hashlib.sha256(raw_bytes).hexdigest()))
        document = _decode_document(raw_bytes, file_path)
        version = document.get("openapi")
        swagger = document.get("swagger")
        is_swagger = swagger == "2.0"
        if not is_swagger and not (
            isinstance(version, str) and version.startswith(("3.0.", "3.1."))
        ):
            raise FixtureSourceError(
                f"{file_path} must be Swagger 2.0 or OpenAPI 3.0/3.1"
            )
        _extract_operations(document, is_swagger, operations, file_path)

    missing = set(config.operations) - set(operations)
    if missing:
        raise FixtureSourceError(
            f"configured operation IDs not found: {sorted(missing)}"
        )
    operations = {key: operations[key] for key in sorted(config.operations)}

    model_classes: dict[str, type[Any]] = {}
    model_schemas: dict[str, dict[str, Any]] = {}
    with _python_paths([config.project.root, *config.project.python_paths]):
        if config.sources.pydantic is not None:
            for alias, reference in config.sources.pydantic.models.items():
                model = model_overrides.get(alias) or _import_reference(reference)
                if not isinstance(model, type) or not issubclass(model, BaseModel):
                    raise FixtureSourceError(
                        f"Pydantic model {alias!r} is not a Pydantic BaseModel"
                    )
                model_classes[alias] = model
                model_schema = model.model_json_schema()
                model_schemas[alias] = _SchemaResolver(
                    model_schema, Path(reference)
                ).resolve(model_schema)

        if config.sources.django is not None:
            try:
                import django
            except ImportError as error:
                raise FixtureSourceError(
                    "Django model sources require `verisim[django]`"
                ) from error
            from django.conf import settings

            if not settings.configured:
                import os

                os.environ.setdefault(
                    "DJANGO_SETTINGS_MODULE", config.sources.django.settings_module
                )
                django.setup()
            for alias, reference in config.sources.django.models.items():
                model = model_overrides.get(alias) or _import_reference(reference)
                if not hasattr(model, "_meta"):
                    raise FixtureSourceError(
                        f"configured Django model {alias!r} has no model metadata"
                    )
                model_classes[alias] = model
                model_schemas[alias] = _django_model_schema(model)

    for model in model_classes.values():
        try:
            model_path = Path(inspect.getfile(model)).resolve()
        except (TypeError, OSError):
            continue
        if model_path.is_file():
            digests.append(
                (str(model_path), hashlib.sha256(model_path.read_bytes()).hexdigest())
            )
            if model_path not in files:
                files = (*files, model_path)

    for operation_id, operation_config in config.operations.items():
        alias = operation_config.request_model
        if alias is None:
            continue
        model_schema = model_schemas[alias]
        operation = operations[operation_id]
        if operation.request_schema is None:
            raise FixtureSourceError(
                f"operation {operation_id!r} has no request schema for model {alias!r}"
            )
        try:
            request_schema = intersect(operation.request_schema, model_schema)
        except ValueError as error:
            raise FixtureSourceError(f"operation {operation_id!r}: {error}") from error
        operations[operation_id] = OperationContract(
            **{
                **operation.__dict__,
                "request_schema": request_schema,
            }
        )

    snapshot = json.dumps(
        {
            "revision": config.project.revision,
            "files": sorted(digests),
            "operations": {
                key: operation.__dict__ for key, operation in sorted(operations.items())
            },
            "models": {
                alias: hashlib.sha256(
                    json.dumps(schema, sort_keys=True, default=str).encode()
                ).hexdigest()
                for alias, schema in sorted(model_schemas.items())
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return LoadedSources(
        operations=operations,
        model_classes=model_classes,
        model_schemas=model_schemas,
        input_fingerprint=f"sha256:{hashlib.sha256(snapshot).hexdigest()}",
        files=files,
    )


def _decode_document(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            import yaml

            value = yaml.safe_load(raw)
        else:
            value = json.loads(raw)
    except ImportError as error:
        raise FixtureSourceError("YAML OpenAPI documents require PyYAML") from error
    except Exception as error:
        raise FixtureSourceError(f"invalid OpenAPI document {path}: {error}") from error
    if not isinstance(value, dict):
        raise FixtureSourceError(f"OpenAPI document {path} must contain an object")
    return value


def _extract_operations(
    document: dict[str, Any],
    is_swagger: bool,
    result: dict[str, OperationContract],
    path: Path,
) -> None:
    for route, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        common_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            method_upper = method.upper()
            if method_upper not in {
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "HEAD",
                "OPTIONS",
            }:
                continue
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                continue
            if operation_id in result:
                raise FixtureSourceError(f"duplicate operationId {operation_id!r}")
            parameters = [*common_parameters, *operation.get("parameters", [])]
            body_schema: dict[str, Any] | None = None
            content_type: str | None = None
            body_required = False
            if is_swagger:
                body_parameters = [p for p in parameters if p.get("in") == "body"]
                parameters = [p for p in parameters if p.get("in") != "body"]
                if len(body_parameters) > 1:
                    raise FixtureSourceError(
                        f"operation {operation_id!r} has multiple body parameters"
                    )
                if body_parameters:
                    body_schema = body_parameters[0].get("schema")
                    body_required = body_parameters[0].get("required", False)
                    content_type = (
                        operation.get("consumes")
                        or document.get("consumes")
                        or ["application/json"]
                    )[0]
            else:
                request_body = operation.get("requestBody", {})
                body_required = bool(request_body.get("required", False))
                content = request_body.get("content", {})
                selected = next(
                    (
                        (name, value)
                        for name, value in content.items()
                        if name in {"application/json", "application/*+json"}
                    ),
                    next(iter(content.items()), (None, {})),
                )
                content_type, body_entry = selected
                body_schema = (
                    body_entry.get("schema") if isinstance(body_entry, dict) else None
                )
            resolver = _SchemaResolver(document, path)
            normalized_parameters = tuple(
                _normalize_parameter(parameter, resolver, operation_id)
                for parameter in parameters
            )
            normalized_schema = (
                resolver.resolve(body_schema) if body_schema is not None else None
            )
            result[operation_id] = OperationContract(
                operation_id=operation_id,
                method=method_upper,
                path=route,
                parameters=normalized_parameters,
                request_schema=normalized_schema,
                request_content_type=content_type,
                request_required=body_required,
            )


def _normalize_parameter(
    parameter: Any, resolver: _SchemaResolver, operation_id: str
) -> dict[str, Any]:
    if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str):
        raise FixtureSourceError(f"operation {operation_id!r} has an invalid parameter")
    location = parameter.get("in")
    if location not in {"path", "query", "header"}:
        raise FixtureSourceError(
            f"operation {operation_id!r} uses unsupported parameter {location!r}"
        )
    schema = parameter.get("schema")
    if schema is None:  # Swagger 2.0 primitive parameter.
        schema = {
            key: value
            for key, value in parameter.items()
            if key
            in {
                "type",
                "format",
                "enum",
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "exclusiveMaximum",
                "minLength",
                "maxLength",
                "pattern",
                "items",
            }
        }
    return {
        "name": parameter["name"],
        "in": location,
        "required": bool(parameter.get("required", location == "path")),
        "schema": resolver.resolve(schema),
    }


class _SchemaResolver:
    def __init__(self, document: dict[str, Any], path: Path) -> None:
        self.document = document
        self.path = path

    def resolve(self, schema: Any, seen: frozenset[str] = frozenset()) -> Any:
        if isinstance(schema, list):
            return [self.resolve(item, seen) for item in schema]
        if not isinstance(schema, dict):
            return schema
        ref = schema.get("$ref")
        if ref is not None:
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise FixtureSourceError(
                    f"remote or invalid $ref {ref!r} in {self.path}"
                )
            if ref in seen:
                raise FixtureSourceError(f"cyclic $ref {ref!r} cannot be normalized")
            target: Any = self.document
            for component in ref[2:].split("/"):
                component = component.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or component not in target:
                    raise FixtureSourceError(f"unresolved $ref {ref!r} in {self.path}")
                target = target[component]
            if not isinstance(target, dict):
                raise FixtureSourceError(
                    f"$ref {ref!r} does not point to a schema object"
                )
            expanded = self.resolve(target, seen | {ref})
            siblings = {key: value for key, value in schema.items() if key != "$ref"}
            return {**expanded, **self.resolve(siblings, seen)}
        supported = {
            "$defs",
            "definitions",
            "type",
            "title",
            "description",
            "default",
            "enum",
            "const",
            "format",
            "properties",
            "required",
            "items",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "examples",
            "example",
            "nullable",
            "readOnly",
            "writeOnly",
            "deprecated",
            "xml",
            "externalDocs",
            "additionalProperties",
            "anyOf",
        }
        unsupported = {
            key for key in schema if key not in supported and not key.startswith("x-")
        }
        if unsupported:
            raise FixtureSourceError(
                f"unsupported schema keywords: {sorted(unsupported)}"
            )
        schema_type = schema.get("type")
        supported_types = {
            "object",
            "array",
            "string",
            "integer",
            "number",
            "boolean",
            "null",
        }
        if isinstance(schema_type, list):
            valid_type = bool(schema_type) and set(schema_type) <= supported_types
        else:
            valid_type = schema_type is None or schema_type in supported_types
        if not valid_type:
            raise FixtureSourceError(f"unsupported schema type {schema_type!r}")
        if schema.get("uniqueItems") is True:
            raise FixtureSourceError("unsupported schema keyword: uniqueItems")
        resolved: dict[str, Any] = {}
        for key, value in schema.items():
            if key in {"properties", "$defs", "definitions"} and isinstance(
                value, dict
            ):
                resolved[key] = {
                    name: self.resolve(child, seen) for name, child in value.items()
                }
            elif key == "items" and isinstance(value, (dict, list)):
                resolved[key] = self.resolve(value, seen)
            elif key == "anyOf":
                if not isinstance(value, list) or not value:
                    raise FixtureSourceError("anyOf must contain schema alternatives")
                resolved[key] = [self.resolve(item, seen) for item in value]
            elif key == "additionalProperties" and isinstance(value, dict):
                resolved[key] = self.resolve(value, seen)
            else:
                resolved[key] = value
        return resolved


def _django_model_schema(model: type[Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in model._meta.concrete_fields:
        if getattr(field, "auto_created", False) and not getattr(
            field, "primary_key", False
        ):
            continue
        name = field.name
        internal_type = field.get_internal_type()
        json_type = (
            "integer"
            if "IntegerField" in internal_type
            or internal_type in {"AutoField", "BigAutoField", "SmallAutoField"}
            else (
                "number"
                if internal_type in {"FloatField", "DecimalField"}
                else "boolean" if internal_type == "BooleanField" else "string"
            )
        )
        if getattr(field, "primary_key", False):
            properties[name] = {"type": json_type, "default": 1001}
            continue
        if getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False):
            continue
        properties[name] = {"type": json_type}
        if internal_type == "JSONField":
            properties[name] = {"type": "object", "properties": {}}
        formats = {
            "EmailField": "email",
            "DateField": "date",
            "DateTimeField": "date-time",
            "UUIDField": "uuid",
            "URLField": "uri",
        }
        format_type = (
            field.__class__.__name__
            if field.__class__.__name__ in formats
            else internal_type
        )
        if format_type in formats:
            properties[name]["format"] = formats[format_type]
        if field.has_default():
            if not callable(field.default):
                properties[name]["default"] = field.default
            elif internal_type not in {"DateField", "DateTimeField", "UUIDField"}:
                if field.default in {dict, list}:
                    properties[name]["default"] = field.default()
                else:
                    raise FixtureSourceError(
                        f"callable default for {model.__name__}.{name} requires "
                        "an explicit deterministic model adapter"
                    )
        for validator in field.validators:
            bound = getattr(validator, "limit_value", None)
            if isinstance(bound, (int, float)):
                if validator.__class__.__name__ == "MinValueValidator":
                    properties[name]["minimum"] = bound
                elif validator.__class__.__name__ == "MaxValueValidator":
                    properties[name]["maximum"] = bound
        if getattr(field, "choices", None):
            properties[name]["enum"] = [choice[0] for choice in field.choices]
        if getattr(field, "max_length", None):
            properties[name]["maxLength"] = field.max_length
        if getattr(field, "min_length", None):
            properties[name]["minLength"] = field.min_length
        if getattr(field, "max_digits", None):
            properties[name]["maximum"] = 10**field.max_digits - 1
        if getattr(field, "max_value", None) is not None:
            properties[name]["maximum"] = field.max_value
        if getattr(field, "min_value", None) is not None:
            properties[name]["minimum"] = field.min_value
        if field.null:
            properties[name]["type"] = [json_type, "null"]
        if not field.blank and not field.null or field.has_default():
            required.append(name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


__all__ = ["FixtureSourceError", "LoadedSources", "OperationContract", "load_sources"]
