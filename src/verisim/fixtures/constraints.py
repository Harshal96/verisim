from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class ConstraintError(ValueError):
    """A branch predicate is invalid or cannot be evaluated safely."""


_OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "exists"}
_ROOTS = {"request", "fixtures", "actor", "environment"}
_MISSING = object()


def validate_expression(expression: Any) -> None:
    if not isinstance(expression, Mapping):
        raise ConstraintError("constraint expression must be an object")
    if set(expression) == {"all"} or set(expression) == {"any"}:
        values = expression[next(iter(expression))]
        if not isinstance(values, list):
            raise ConstraintError("all/any constraints require a list")
        for value in values:
            validate_expression(value)
        return
    if set(expression) == {"not"}:
        validate_expression(expression["not"])
        return
    if not {"path", "op"} <= set(expression) or set(expression) - {
        "path",
        "op",
        "value",
    }:
        raise ConstraintError(
            "constraint leaves require path and op, with optional value"
        )
    path = expression["path"]
    if not isinstance(path, str) or len(path.split(".")) < 2:
        raise ConstraintError("constraint path must be a dotted path")
    if path.split(".", 1)[0] not in _ROOTS:
        raise ConstraintError(f"unknown constraint path root in {path!r}")
    if expression["op"] not in _OPERATORS:
        raise ConstraintError(f"unknown constraint operator {expression['op']!r}")
    op = expression["op"]
    if op == "exists":
        if type(expression.get("value")) is not bool:
            raise ConstraintError("exists requires a boolean value")
    elif "value" not in expression:
        raise ConstraintError(f"operator {op!r} requires a value")
    if op in {"in", "not_in"} and not isinstance(expression["value"], list):
        raise ConstraintError(f"operator {op!r} requires a list value")
    if op in {"lt", "lte", "gt", "gte"} and not _is_number(expression["value"]):
        raise ConstraintError(f"operator {op!r} requires a numeric value")


def evaluate(expression: Mapping[str, Any], scenario: Mapping[str, Any]) -> bool:
    validate_expression(expression)
    if "all" in expression:
        return all(evaluate(item, scenario) for item in expression["all"])
    if "any" in expression:
        return any(evaluate(item, scenario) for item in expression["any"])
    if "not" in expression:
        return not evaluate(expression["not"], scenario)
    actual = _resolve(scenario, expression["path"])
    op = expression["op"]
    expected = expression.get("value")
    if op == "exists":
        return (actual is not _MISSING) is expected
    if actual is _MISSING:
        return False
    if op == "eq":
        return type(actual) is type(expected) and actual == expected
    if op == "ne":
        return type(actual) is not type(expected) or actual != expected
    if op in {"in", "not_in"}:
        matched = any(
            type(actual) is type(value) and actual == value for value in expected
        )
        return matched if op == "in" else not matched
    if not _is_number(actual):
        raise ConstraintError(f"operator {op!r} requires a numeric path value")
    return {
        "lt": actual < expected,
        "lte": actual <= expected,
        "gt": actual > expected,
        "gte": actual >= expected,
    }[op]


def _resolve(root: Mapping[str, Any], path: str) -> Any:
    parts = path.split(".")
    if parts[0] == "request" and (
        len(parts) < 3
        or parts[1] not in {"body", "query", "path_parameters", "headers"}
    ):
        raise ConstraintError(f"unsupported request path {path!r}")
    current: Any = root
    for component in parts:
        if isinstance(current, Mapping):
            current = current.get(component, _MISSING)
        elif (
            isinstance(current, Sequence)
            and not isinstance(current, (str, bytes))
            and component.isdigit()
        ):
            index = int(component)
            current = current[index] if index < len(current) else _MISSING
        else:
            return _MISSING
        if current is _MISSING:
            return _MISSING
    return current


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


__all__ = ["ConstraintError", "evaluate", "validate_expression"]
