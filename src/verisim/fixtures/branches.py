from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Callable

from verisim.fixtures.constraints import ConstraintError, validate_expression


class BranchCatalogError(ValueError):
    """The provider returned an incomplete or inconsistent branch catalog."""


@dataclass(frozen=True)
class BranchTarget:
    id: str
    operation_id: str
    arc: dict[str, Any] | None
    constraints: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class BranchCatalog:
    source_revision: str
    operations: tuple[str, ...]
    targets: tuple[BranchTarget, ...]

    @property
    def target_ids(self) -> frozenset[str]:
        return frozenset(target.id for target in self.targets)

    def targets_for(self, operation_id: str) -> tuple[BranchTarget, ...]:
        return tuple(t for t in self.targets if t.operation_id == operation_id)


def _resolve(reference: str) -> Callable[..., Any]:
    module, _, attribute = reference.partition(":")
    try:
        value: Any = importlib.import_module(module)
        for name in attribute.split("."):
            value = getattr(value, name)
    except (ImportError, AttributeError) as error:
        raise BranchCatalogError(
            f"cannot import branch adapter {reference!r}: {error}"
        ) from error
    if not callable(value):
        raise BranchCatalogError(f"branch adapter {reference!r} is not callable")
    return value


def load_catalog(
    config: Any, sources: Any, *, provider: Callable[..., Any] | None = None
) -> BranchCatalog:
    selected = sorted(config.operations)
    context = MappingProxyType(
        {
            "project_root": str(config.project.root),
            "source_revision": config.project.revision,
            "selected_operations": tuple(selected),
            "input_fingerprint": sources.input_fingerprint,
            "source_files": tuple(str(path) for path in sources.files),
        }
    )
    callback = provider or _resolve(config.branches.adapter)
    try:
        raw = callback(options=dict(config.branches.options), context=context)
    except Exception as error:
        raise BranchCatalogError(f"branch adapter failed: {error}") from error
    return validate_catalog(raw, selected, config.project.revision)


def validate_catalog(raw: Any, selected: list[str], revision: str) -> BranchCatalog:
    if not isinstance(raw, Mapping):
        raise BranchCatalogError("branch catalog must be an object")
    if type(raw.get("version")) is not int or raw.get("version") != 1:
        raise BranchCatalogError("branch catalog version must be 1")
    if raw.get("source_revision") != revision:
        raise BranchCatalogError(
            "branch catalog source revision does not match project revision"
        )
    scope = raw.get("scope")
    if not isinstance(scope, Mapping) or scope.get("complete") is not True:
        raise BranchCatalogError("branch catalog scope must assert complete=true")
    scope_operations = scope.get("operations")
    if (
        not isinstance(scope_operations, list)
        or any(not isinstance(value, str) for value in scope_operations)
        or sorted(scope_operations) != selected
    ):
        raise BranchCatalogError(
            "catalog scope operations must match selected operation scope exactly"
        )
    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise BranchCatalogError("branch catalog must contain at least one target")
    targets: list[BranchTarget] = []
    ids: set[str] = set()
    by_operation = {operation: 0 for operation in selected}
    for item in raw_targets:
        if not isinstance(item, Mapping):
            raise BranchCatalogError("branch targets must be objects")
        target_id = item.get("id")
        operation_id = item.get("operation_id")
        if not isinstance(target_id, str) or not target_id:
            raise BranchCatalogError("branch target id must be a non-empty string")
        if target_id in ids:
            raise BranchCatalogError(f"duplicate branch target id {target_id!r}")
        if not isinstance(operation_id, str) or operation_id not in by_operation:
            raise BranchCatalogError(
                f"branch target {target_id!r} references unselected operation"
            )
        ids.add(target_id)
        by_operation[operation_id] += 1
        arc = item.get("arc")
        if arc is not None:
            if not isinstance(arc, Mapping) or not isinstance(arc.get("file"), str):
                raise BranchCatalogError(f"branch target {target_id!r} has invalid arc")
            arc_path = PurePosixPath(arc["file"])
            if arc_path.is_absolute() or ".." in arc_path.parts:
                raise BranchCatalogError(
                    f"branch target {target_id!r} arc path must be project-relative"
                )
            if (
                type(arc.get("from_line")) is not int
                or type(arc.get("to_line")) is not int
            ):
                raise BranchCatalogError(
                    f"branch target {target_id!r} has invalid arc lines"
                )
            if arc["from_line"] < 1 or arc["to_line"] < 1:
                raise BranchCatalogError(
                    f"branch target {target_id!r} arc lines must be positive"
                )
            arc = dict(arc)
        constraints = item.get("constraints", [])
        if not isinstance(constraints, list):
            raise BranchCatalogError(
                f"branch target {target_id!r} constraints must be a list"
            )
        try:
            for constraint in constraints:
                validate_expression(constraint)
        except ConstraintError as error:
            raise BranchCatalogError(f"branch target {target_id!r}: {error}") from error
        targets.append(
            BranchTarget(
                target_id, operation_id, arc, tuple(dict(c) for c in constraints)
            )
        )
    missing = [op for op, count in by_operation.items() if count == 0]
    if missing:
        raise BranchCatalogError(
            f"selected operations have no branch targets: {sorted(missing)}"
        )
    return BranchCatalog(
        revision, tuple(selected), tuple(sorted(targets, key=lambda t: t.id))
    )


__all__ = [
    "BranchCatalog",
    "BranchCatalogError",
    "BranchTarget",
    "load_catalog",
    "validate_catalog",
]
