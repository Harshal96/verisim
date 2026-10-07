from __future__ import annotations

import copy
import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionRecord:
    scenario_id: str
    operation_id: str
    execution_valid: bool
    coverage_valid: bool
    observed_branch_ids: frozenset[str]
    checks_passed: bool
    diagnostics: tuple[str, ...]
    receipt: dict[str, Any]


@dataclass(frozen=True)
class ExecutionResults:
    records: tuple[ExecutionRecord, ...]

    @property
    def by_scenario_id(self) -> dict[str, ExecutionRecord]:
        return {record.scenario_id: record for record in self.records}


def resolve_runner(reference: str) -> Callable[..., Any]:
    module, _, attribute = reference.partition(":")
    value: Any = importlib.import_module(module)
    for name in attribute.split("."):
        value = getattr(value, name)
    if not callable(value):
        raise TypeError(f"configured runner {reference!r} is not callable")
    return value


def execute_candidates(
    scenarios: Sequence[Any],
    runner: Callable[..., Any],
    *,
    source_fingerprint: str,
    targets: Mapping[str, set[str] | frozenset[str]],
    source_revision: str,
    options: Mapping[str, Any] | None = None,
    catalog_targets: Sequence[Mapping[str, Any]] = (),
) -> ExecutionResults:
    """Run each candidate once and retain only trustworthy coverage evidence."""
    records: list[ExecutionRecord] = []
    context = {
        "source_revision": source_revision,
        "input_fingerprint": source_fingerprint,
        "target_ids_by_operation": {
            key: sorted(value) for key, value in targets.items()
        },
        "catalog_targets": [dict(target) for target in catalog_targets],
        "options": dict(options or {}),
    }
    for scenario in scenarios:
        scenario_data = copy.deepcopy(
            scenario.to_dict() if hasattr(scenario, "to_dict") else dict(scenario)
        )
        scenario_id = scenario_data.get("id", "")
        operation_id = scenario_data.get("operation_id", "")
        try:
            scenario_context = copy.deepcopy(context)
            scenario_context["effective_clock"] = scenario_data.get("clock")
            raw = runner(scenario_data, context=scenario_context)
        except Exception as error:
            raw = {
                "diagnostics": [f"runner raised {error.__class__.__name__}: {error}"]
            }
        records.append(
            _validate_receipt(
                raw,
                scenario_id=scenario_id,
                operation_id=operation_id,
                source_fingerprint=source_fingerprint,
                source_revision=source_revision,
                allowed_targets=frozenset(targets.get(operation_id, set())),
            )
        )
    return ExecutionResults(tuple(records))


def _validate_receipt(
    raw: Any,
    *,
    scenario_id: str,
    operation_id: str,
    source_fingerprint: str,
    source_revision: str,
    allowed_targets: frozenset[str],
) -> ExecutionRecord:
    diagnostics: list[str] = []
    if not isinstance(raw, Mapping):
        raw = {}
        diagnostics.append("runner receipt must be an object")
    if type(raw.get("version")) is not int or raw.get("version") != 1:
        diagnostics.append("receipt version must be 1")
    required_fields = {
        "scenario_id",
        "operation_id",
        "source_revision",
        "input_fingerprint",
        "execution_valid",
        "coverage_valid",
        "measured_invocations",
        "isolated",
        "observed_branch_ids",
        "checks_passed",
        "diagnostics",
    }
    missing_fields = required_fields - set(raw)
    if missing_fields:
        diagnostics.append(f"receipt is missing fields: {sorted(missing_fields)}")
    checks = raw.get("checks_passed")
    execution_valid = raw.get("execution_valid")
    coverage_flag = raw.get("coverage_valid")
    if raw.get("scenario_id") != scenario_id:
        diagnostics.append("scenario ID mismatch")
    if raw.get("operation_id") != operation_id:
        diagnostics.append("operation ID mismatch")
    if raw.get("source_revision") != source_revision:
        diagnostics.append("source revision mismatch")
    if raw.get("input_fingerprint") != source_fingerprint:
        diagnostics.append("input fingerprint mismatch")
    if (
        type(execution_valid) is not bool
        or type(coverage_flag) is not bool
        or type(checks) is not bool
    ):
        diagnostics.append("receipt flags must be booleans")
    if execution_valid is not True:
        diagnostics.append("execution was not valid")
    if (
        type(raw.get("measured_invocations")) is not int
        or raw.get("measured_invocations") != 1
    ):
        diagnostics.append("receipt must describe exactly one measured invocation")
    if raw.get("isolated") is not True:
        diagnostics.append("runner did not confirm isolated execution")
    observed = raw.get("observed_branch_ids", [])
    observed_valid = isinstance(observed, list) and all(
        isinstance(value, str) for value in observed
    )
    if not observed_valid:
        diagnostics.append("observed_branch_ids must be a list of strings")
        observed = []
    unknown = set(observed) - allowed_targets
    if unknown:
        diagnostics.append(f"receipt contains unknown branch IDs: {sorted(unknown)}")
    details = raw.get("diagnostics", [])
    diagnostics_valid = isinstance(details, list) and all(
        isinstance(value, str) for value in details
    )
    if not diagnostics_valid:
        diagnostics.append("diagnostics must be a list of strings")
        details = []
    diagnostics.extend(details)
    identity_valid = (
        raw.get("scenario_id") == scenario_id
        and raw.get("operation_id") == operation_id
        and raw.get("source_revision") == source_revision
        and raw.get("input_fingerprint") == source_fingerprint
    )
    measurement_valid = (
        execution_valid is True
        and coverage_flag is True
        and type(raw.get("measured_invocations")) is int
        and raw.get("measured_invocations") == 1
        and raw.get("isolated") is True
        and not unknown
    )
    structure_valid = (
        type(raw.get("version")) is int
        and raw.get("version") == 1
        and type(execution_valid) is bool
        and type(coverage_flag) is bool
        and type(checks) is bool
        and observed_valid
        and diagnostics_valid
        and not missing_fields
    )
    coverage_valid = identity_valid and measurement_valid and structure_valid
    normalized = {
        "version": 1,
        "scenario_id": scenario_id,
        "operation_id": operation_id,
        "source_revision": source_revision,
        "input_fingerprint": source_fingerprint,
        "execution_valid": execution_valid is True,
        "coverage_valid": coverage_valid,
        "measured_invocations": (
            raw.get("measured_invocations")
            if type(raw.get("measured_invocations")) is int
            else None
        ),
        "isolated": raw.get("isolated") is True,
        "observed_branch_ids": sorted(set(observed)) if coverage_valid else [],
        "checks_passed": checks is True,
        "diagnostics": diagnostics,
    }
    return ExecutionRecord(
        scenario_id,
        operation_id,
        execution_valid is True,
        coverage_valid,
        frozenset(normalized["observed_branch_ids"]),
        checks is True,
        tuple(diagnostics),
        normalized,
    )


__all__ = [
    "ExecutionRecord",
    "ExecutionResults",
    "execute_candidates",
    "resolve_runner",
]
