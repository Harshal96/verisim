from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import random
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from verisim.fixtures.codec import encode
from verisim.fixtures.constraints import ConstraintError, evaluate, validate_expression
from verisim.fixtures.schema import intersect, matches


@dataclass(frozen=True)
class Scenario:
    id: str
    operation_id: str
    source_revision: str
    seed: int
    clock: str
    request: dict[str, Any]
    fixture_rows: tuple[dict[str, Any], ...]
    actor: dict[str, Any]
    environment: dict[str, Any]
    setup: tuple[dict[str, Any], ...]
    expectations: dict[str, Any]
    target_branch_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "id": self.id,
            "operation_id": self.operation_id,
            "source_revision": self.source_revision,
            "seed": self.seed,
            "clock": self.clock,
            "request": self.request,
            "fixture_rows": list(self.fixture_rows),
            "actor": self.actor,
            "environment": self.environment,
            "setup": list(self.setup),
            "expectations": self.expectations,
            "target_branch_ids": list(self.target_branch_ids),
        }


@dataclass(frozen=True)
class CandidatePool:
    scenarios: tuple[Scenario, ...]
    candidate_limit: int
    limit_reached: bool
    diagnostics: tuple[dict[str, Any], ...] = ()


class CandidateGenerationError(ValueError):
    """A candidate cannot satisfy the configured schema/model contract."""


def generate_candidates(config: Any, sources: Any, catalog: Any) -> CandidatePool:
    """Construct, validate and deduplicate a finite pool; hints are never evidence."""
    generated: dict[str, Scenario] = {}
    diagnostics: list[dict[str, Any]] = []
    limit = config.generation.candidate_limit
    clock = config.generation.clock
    clock_text = (
        clock.isoformat().replace("+00:00", "Z")
        if isinstance(clock, datetime)
        else str(clock)
    )
    seed = config.generation.seed if config.generation.seed is not None else 0
    work = [
        (s.operation_id, dict(s.values), dict(s.expectations), (), ())
        for s in config.generation.candidates
    ]
    for operation_id in sorted(config.operations):
        targets = sorted(
            (t for t in catalog.targets if t.operation_id == operation_id),
            key=lambda t: t.id,
        )
        if not targets:
            work.append((operation_id, {}, {}, (), ()))
        for target in targets:
            work.append((operation_id, {}, {}, (target.id,), tuple(target.constraints)))
    limit_reached = False
    for operation_id, values, expectations, hinted_ids, expressions in work:
        operation_config = config.operations[operation_id]
        contract = sources.operations[operation_id]
        rng = random.Random(seed)
        try:
            request = {
                "method": contract.method,
                "path": contract.path,
                "path_parameters": _parameter_values(
                    contract.parameters, "path_parameters", rng, clock_text
                ),
                "query": _parameter_values(
                    contract.parameters, "query", rng, clock_text
                ),
                "headers": _parameter_values(
                    contract.parameters, "header", rng, clock_text
                ),
                "body": (
                    _make_value(contract.request_schema, rng, clock_text)
                    if contract.request_schema
                    else None
                ),
            }
            fixture_rows = _fixture_rows(operation_config, sources, rng, clock_text)
            scenario = {
                "request": request,
                "fixtures": {
                    r["ref"]: {**r["fields"], **r["relations"]} for r in fixture_rows
                },
                "actor": {},
                "environment": {},
            }
            _apply_values(scenario, values)
            for expression in expressions:
                validate_expression(expression)
            if expressions:
                scenario = _satisfy(expressions, scenario)
                request = scenario["request"]
            for destination, origin in operation_config.bindings.items():
                value, found = _get_path(scenario, origin)
                if not found:
                    parts = origin.split(".")
                    removed_row = (
                        len(parts) >= 3
                        and parts[0] == "fixtures"
                        and parts[1] not in scenario["fixtures"]
                        and any(row["ref"] == parts[1] for row in fixture_rows)
                    )
                    if removed_row and _get_path(scenario, destination)[1]:
                        # The generated ID now intentionally addresses a missing row.
                        continue
                    raise CandidateGenerationError(
                        f"binding source {origin!r} is absent"
                    )
                explicit = destination in values or any(
                    destination in _leaves(e) for e in expressions
                )
                current, present = _get_path(scenario, destination)
                if (
                    explicit
                    and present
                    and (type(current) is not type(value) or current != value)
                ):
                    raise CandidateGenerationError(
                        f"binding conflict at {destination!r}"
                    )
                _set_path(scenario, destination, value)
            if expressions and not all(evaluate(e, scenario) for e in expressions):
                raise CandidateGenerationError(
                    "bindings conflict with branch constraints"
                )
            fixture_rows = [r for r in fixture_rows if r["ref"] in scenario["fixtures"]]
            for row in fixture_rows:
                state = scenario["fixtures"][row["ref"]]
                if not isinstance(state, dict):
                    raise CandidateGenerationError(
                        "fixture row state must be a mapping"
                    )
                model = sources.model_classes.get(row["model"])
                relation_names = set(row["relations"])
                if model is not None and hasattr(model, "_meta"):
                    relation_names |= {
                        field.name
                        for field in model._meta.concrete_fields
                        if getattr(field, "many_to_one", False)
                        or getattr(field, "one_to_one", False)
                    }
                row["fields"] = {
                    k: v for k, v in state.items() if k not in relation_names
                }
                row["relations"] = {
                    k: v for k, v in state.items() if k in relation_names
                }
            _validate_fixture_rows(fixture_rows, sources)
            request_body = request["body"]
            request_model = operation_config.request_model
            if request_model and request_model in sources.model_classes:
                try:
                    request["body"] = (
                        sources.model_classes[request_model]
                        .model_validate(request_body)
                        .model_dump(mode="json")
                    )
                except Exception:
                    # Invalid requests can exercise API validation branches.
                    pass
            envelope = {
                "operation_id": operation_id,
                "source_revision": config.project.revision,
                "seed": seed,
                "clock": clock_text,
                "request": request,
                "fixture_rows": fixture_rows,
                "actor": scenario["actor"],
                "environment": scenario["environment"],
                "setup": [],
                "expectations": expectations,
            }
            canonical = json.dumps(
                encode(envelope), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            scenario_id = (
                "scenario-" + hashlib.sha256(canonical.encode()).hexdigest()[:20]
            )
            if scenario_id in generated:
                prior = generated[scenario_id]
                generated[scenario_id] = replace(
                    prior,
                    target_branch_ids=tuple(
                        sorted(set(prior.target_branch_ids) | set(hinted_ids))
                    ),
                )
                continue
            if len(generated) >= limit:
                limit_reached = True
                continue
            generated[scenario_id] = Scenario(
                scenario_id,
                operation_id,
                config.project.revision,
                seed,
                clock_text,
                request,
                tuple(fixture_rows),
                scenario["actor"],
                scenario["environment"],
                (),
                expectations,
                hinted_ids,
            )
        except (CandidateGenerationError, ConstraintError) as error:
            diagnostics.append(
                {
                    "operation_id": operation_id,
                    "target_branch_ids": list(hinted_ids),
                    "reason": str(error),
                }
            )
    return CandidatePool(
        tuple(generated[k] for k in sorted(generated)),
        limit,
        limit_reached,
        tuple(diagnostics),
    )


def _make_value(
    schema: Any, rng: random.Random, clock: str = "2026-01-01T00:00:00Z"
) -> Any:
    if not isinstance(schema, dict):
        return None
    if "default" in schema and matches(schema, schema["default"]):
        return copy.deepcopy(schema["default"])
    if "const" in schema:
        if not matches(schema, schema["const"]):
            raise CandidateGenerationError("constant contradicts schema constraints")
        return schema["const"]
    if schema.get("enum"):
        choices = [value for value in schema["enum"] if matches(schema, value)]
        if not choices:
            raise CandidateGenerationError("enum has no schema-valid value")
        return choices[0]
    if "anyOf" in schema:
        alternatives = sorted(schema["anyOf"], key=lambda s: s.get("type") == "null")
        errors = []
        for alternative in alternatives:
            try:
                siblings = {k: v for k, v in schema.items() if k != "anyOf"}
                return _make_value(intersect(siblings, alternative), rng, clock)
            except (CandidateGenerationError, ValueError) as error:
                errors.append(str(error))
        raise CandidateGenerationError(f"anyOf has no generated value: {errors}")
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "null")
    if schema_type == "object" or "properties" in schema:
        return {
            key: _make_value(child, rng, clock)
            for key, child in schema.get("properties", {}).items()
            if key in schema.get("required", []) or "default" in child
        }
    if schema_type == "array":
        count = max(0, schema.get("minItems", 0))
        if count > schema.get("maxItems", count):
            raise CandidateGenerationError("array schema has incompatible item bounds")
        if count > 1000:
            raise CandidateGenerationError(
                "array schema exceeds the generation safety bound"
            )
        return [_make_value(schema.get("items", {}), rng, clock) for _ in range(count)]
    if schema_type in {"integer", "number"}:
        lower, upper = schema.get("minimum", -math.inf), schema.get("maximum", math.inf)
        exlo, exhi = schema.get("exclusiveMinimum"), schema.get("exclusiveMaximum")
        if exlo is not None and exlo is not False:
            bound = lower if exlo is True else exlo
            lower = max(
                lower,
                (
                    math.floor(bound) + 1
                    if schema_type == "integer"
                    else math.nextafter(bound, math.inf)
                ),
            )
        if schema_type == "integer" and math.isfinite(lower):
            lower = math.ceil(lower)
        if exhi is not None and exhi is not False:
            bound = upper if exhi is True else exhi
            upper = min(
                upper,
                (
                    math.ceil(bound) - 1
                    if schema_type == "integer"
                    else math.nextafter(bound, -math.inf)
                ),
            )
        if schema_type == "integer" and math.isfinite(upper):
            upper = math.floor(upper)
        value = max(lower, min(1, upper))
        if lower > upper or not math.isfinite(value):
            raise CandidateGenerationError(
                f"{schema_type} schema has no generated value"
            )
        return int(value) if schema_type == "integer" else float(value)
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        minimum = schema.get("minLength", 0)
        maximum = schema.get("maxLength", max(minimum, 1))
        if minimum > maximum:
            raise CandidateGenerationError(
                "string schema has incompatible length bounds"
            )
        formats = {
            "email": "user@example.invalid",
            "uuid": "00000000-0000-4000-8000-000000000001",
            "uri": "https://example.invalid/",
            "date": clock[:10],
            "date-time": clock,
        }
        if schema.get("format") in formats:
            value = formats[schema["format"]]
            if not minimum <= len(value) <= schema.get("maxLength", math.inf):
                raise CandidateGenerationError(
                    "formatted string does not satisfy length bounds"
                )
            return value
        return "x" * min(max(minimum, 1), maximum)
    if schema_type == "null":
        return None
    return None


def _fixture_rows(
    operation: Any, sources: Any, rng: random.Random, clock: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    refs = operation.fixture_rows or {
        alias: alias for alias in operation.fixture_models
    }
    refs_by_alias: dict[str, list[str]] = {}
    for row_ref, alias in refs.items():
        refs_by_alias.setdefault(alias, []).append(row_ref)
    for index, (row_ref, alias) in enumerate(sorted(refs.items())):
        fields = _make_value(sources.model_schemas.get(alias, {}), rng, clock)
        if not isinstance(fields, dict):
            fields = {}
        model_class = sources.model_classes.get(alias)
        relations: dict[str, Any] = {}
        if model_class is not None and hasattr(model_class, "_meta"):
            for field in model_class._meta.concrete_fields:
                if getattr(field, "primary_key", False):
                    if field.get_internal_type() == "UUIDField":
                        from uuid import UUID

                        fields[field.name] = UUID(int=1001 + index)
                    elif (
                        field.get_internal_type()
                        in {"AutoField", "BigAutoField", "SmallAutoField"}
                        or "IntegerField" in field.get_internal_type()
                    ):
                        fields[field.name] = 1001 + index
                    else:
                        fields[field.name] = str(1001 + index)
            for field in model_class._meta.concrete_fields:
                if not (
                    getattr(field, "many_to_one", False)
                    or getattr(field, "one_to_one", False)
                ):
                    continue
                relation_model = field.remote_field.model
                related_aliases = [
                    candidate_alias
                    for candidate_alias, candidate_model in (
                        sources.model_classes.items()
                    )
                    if candidate_model is relation_model
                    and candidate_alias in refs_by_alias
                ]
                related_refs = sorted(
                    ref
                    for related_alias in related_aliases
                    for ref in refs_by_alias[related_alias]
                    if ref != row_ref
                )
                if len(related_refs) > 1:
                    # Leave ambiguous links for caller values to disambiguate.
                    continue
                if related_refs:
                    relations[field.name] = {"$ref": related_refs[0]}
                elif not field.null and not field.has_default():
                    raise CandidateGenerationError(
                        f"required relation {alias}.{field.name} lacks a fixture row"
                    )
        rows.append(
            {"ref": row_ref, "model": alias, "fields": fields, "relations": relations}
        )
    return rows


def _validate_fixture_rows(rows: list[dict[str, Any]], sources: Any) -> None:
    refs = {r["ref"]: r for r in rows}
    unique_values: dict[tuple[str, str], list[Any]] = {}
    for row in rows:
        model_class = sources.model_classes.get(row["model"])
        if model_class is None or not hasattr(model_class, "_meta"):
            continue
        try:
            instance = model_class(**row["fields"])
        except (TypeError, ValueError) as error:
            raise CandidateGenerationError(
                f"invalid fields for {row['model']}: {error}"
            ) from error
        for field in model_class._meta.concrete_fields:
            if getattr(field, "many_to_one", False) or getattr(
                field, "one_to_one", False
            ):
                relation = row["relations"].get(field.name)
                if relation is not None:
                    if not isinstance(relation, dict) or set(relation) != {"$ref"}:
                        raise CandidateGenerationError(
                            f"relation {row['ref']}.{field.name} needs an explicit $ref"
                        )
                    target = refs.get(relation.get("$ref"))
                    if (
                        target is None
                        or sources.model_classes[target["model"]]
                        is not field.remote_field.model
                    ):
                        raise CandidateGenerationError(
                            f"invalid relation {row['ref']}.{field.name}"
                        )
                elif not field.null and not field.has_default():
                    raise CandidateGenerationError(
                        f"required relation {row['ref']}.{field.name} is absent"
                    )
                continue
            if field.name not in row["fields"]:
                if getattr(field, "has_default", lambda: False)():
                    raise CandidateGenerationError(
                        f"default for {row['model']}.{field.name} was not materialized"
                    )
                if getattr(field, "null", False) or getattr(field, "blank", False):
                    continue
                raise CandidateGenerationError(
                    f"required field {row['model']}.{field.name} is absent"
                )
            try:
                cleaned = field.clean(row["fields"][field.name], instance)
                row["fields"][field.name] = cleaned
                setattr(instance, field.name, cleaned)
            except Exception as error:
                raise CandidateGenerationError(
                    f"{row['model']}.{field.name} failed validation: {error}"
                ) from error
            if getattr(field, "unique", False) and cleaned is not None:
                previous = unique_values.setdefault((row["model"], field.name), [])
                if cleaned in previous:
                    raise CandidateGenerationError(
                        f"duplicate unique field {row['model']}.{field.name}; "
                        "provide distinct seed values"
                    )
                previous.append(cleaned)
        if hasattr(instance, "clean"):
            try:
                instance.clean()
            except Exception as error:
                raise CandidateGenerationError(
                    f"{row['model']} model validation failed: {error}"
                ) from error


def _parameter_values(
    parameters: Any, location: str, rng: random.Random, clock: str
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for parameter in parameters:
        mapped_location = (
            "path_parameters" if parameter["in"] == "path" else parameter["in"]
        )
        if mapped_location != location:
            continue
        if parameter.get("required"):
            result[parameter["name"]] = _make_value(
                parameter.get("schema", {}), rng, clock
            )
    return result


def _leaves(expression: dict) -> dict[str, list[dict]]:
    if "not" in expression:
        return _leaves(expression["not"])
    if "all" in expression or "any" in expression:
        output: dict[str, list[dict]] = {}
        for child in expression.get("all", expression.get("any", [])):
            for path, leaves in _leaves(child).items():
                output.setdefault(path, []).extend(leaves)
        return output
    return {expression["path"]: [expression]}


def _satisfy(expressions: tuple, baseline: dict) -> dict:
    """Search a bounded domain derived from hints, including logical negations."""
    leaves: dict[str, list[dict]] = {}
    for expression in expressions:
        for path, items in _leaves(expression).items():
            leaves.setdefault(path, []).extend(items)
    domains = {}
    for path, items in sorted(leaves.items()):
        current, found = _get_path(baseline, path)
        values = [current] if found else [_DELETE]
        numbers = []
        for item in items:
            expected = item.get("value")
            if item["op"] == "exists":
                values += [_DELETE, current if found else None]
                continue
            candidates = expected if item["op"] in {"in", "not_in"} else [expected]
            for candidate in candidates:
                values.append(candidate)
                if isinstance(candidate, bool):
                    values.append(not candidate)
                elif isinstance(candidate, (int, float)):
                    numbers.append(candidate)
                    values += [
                        candidate - 1,
                        candidate + 1,
                        math.nextafter(candidate, -math.inf),
                        math.nextafter(candidate, math.inf),
                    ]
                elif isinstance(candidate, str):
                    values += [candidate + "x", ""]
                else:
                    values += [None, True, 0, "x", {}, []]
        for low, high in itertools.combinations(sorted(set(numbers)), 2):
            values.append((low + high) / 2)
        values += [_DELETE]
        unique = []
        for value in values:
            if not any(
                type(value) is type(prior) and value == prior for prior in unique
            ):
                unique.append(value)
        domains[path] = unique
    for attempt, values in enumerate(itertools.product(*domains.values())):
        if attempt >= 4096:
            raise CandidateGenerationError(
                "constraint synthesis search bound exhausted; "
                "provide an explicit candidate seed"
            )
        scenario = copy.deepcopy(baseline)
        try:
            _apply_values(scenario, dict(zip(domains, values)))
            if all(evaluate(e, scenario) for e in expressions):
                return scenario
        except (CandidateGenerationError, ConstraintError):
            continue
    raise CandidateGenerationError(
        "constraints have no satisfying value in the synthesized domain"
    )


_DELETE = object()


def _apply_values(scenario: dict[str, Any], values: dict[str, Any]) -> None:
    for path, value in sorted(values.items()):
        if value is _DELETE:
            _delete_path(scenario, path)
        else:
            _set_path(scenario, path, value)


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = root
    for index, component in enumerate(parts[:-1]):
        next_component = parts[index + 1]
        if isinstance(current, dict):
            if component not in current or current[component] is None:
                current[component] = [] if next_component.isdigit() else {}
            current = current[component]
        elif isinstance(current, list) and component.isdigit():
            position = int(component)
            if position > 1000:
                raise CandidateGenerationError("array index exceeds generation bound")
            while len(current) <= position:
                current.append(None)
            if current[position] is None:
                current[position] = [] if next_component.isdigit() else {}
            current = current[position]
        else:
            raise CandidateGenerationError(f"cannot assign constraint path {path!r}")
    final = parts[-1]
    if isinstance(current, dict):
        current[final] = copy.deepcopy(value)
    elif isinstance(current, list) and final.isdigit():
        position = int(final)
        if position > 1000:
            raise CandidateGenerationError("array index exceeds generation bound")
        while len(current) <= position:
            current.append(None)
        current[position] = copy.deepcopy(value)
    else:
        raise CandidateGenerationError(f"cannot assign constraint path {path!r}")


def _delete_path(root: dict[str, Any], path: str) -> None:
    parent, found = _get_path(root, path.rsplit(".", 1)[0])
    if not found:
        return
    final = path.rsplit(".", 1)[1]
    if isinstance(parent, dict):
        parent.pop(final, None)
    elif isinstance(parent, list) and final.isdigit() and int(final) < len(parent):
        parent.pop(int(final))


def _get_path(root: dict[str, Any], path: str) -> tuple[Any, bool]:
    current: Any = root
    for component in path.split("."):
        if isinstance(current, dict) and component in current:
            current = current[component]
        elif (
            isinstance(current, list)
            and component.isdigit()
            and int(component) < len(current)
        ):
            current = current[int(component)]
        else:
            return None, False
    return current, True


__all__ = [
    "CandidateGenerationError",
    "CandidatePool",
    "Scenario",
    "generate_candidates",
]
