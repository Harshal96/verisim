"""Intersection and value checks for the supported request-schema subset."""

from __future__ import annotations

from typing import Any


def matches(schema: dict, value: Any) -> bool:
    if "anyOf" in schema and not any(matches(s, value) for s in schema["anyOf"]):
        return False
    if "const" in schema and (
        type(value) is not type(schema["const"]) or value != schema["const"]
    ):
        return False
    if "enum" in schema and not any(
        type(value) is type(v) and value == v for v in schema["enum"]
    ):
        return False
    kind = schema.get("type")
    types = kind if isinstance(kind, list) else [kind] if kind else []
    if schema.get("nullable"):
        types = [*types, "null"]
    actual = (
        "null"
        if value is None
        else (
            "boolean"
            if isinstance(value, bool)
            else (
                "integer"
                if isinstance(value, int)
                else (
                    "number"
                    if isinstance(value, float)
                    else (
                        "string"
                        if isinstance(value, str)
                        else (
                            "object"
                            if isinstance(value, dict)
                            else "array" if isinstance(value, list) else "unknown"
                        )
                    )
                )
            )
        )
    )
    if (
        types
        and actual not in types
        and not (actual == "integer" and "number" in types)
    ):
        return False
    if actual in {"integer", "number"}:
        if value < schema.get("minimum", float("-inf")) or value > schema.get(
            "maximum", float("inf")
        ):
            return False
        for key, inclusive_key, less in [
            ("exclusiveMinimum", "minimum", True),
            ("exclusiveMaximum", "maximum", False),
        ]:
            bound = schema.get(key)
            if bound is None or bound is False:
                continue
            bound = schema.get(inclusive_key) if bound is True else bound
            if bound is not None and (value <= bound if less else value >= bound):
                return False
    if actual == "string" and not schema.get("minLength", 0) <= len(
        value
    ) <= schema.get("maxLength", float("inf")):
        return False
    if actual == "array":
        if (
            not schema.get("minItems", 0)
            <= len(value)
            <= schema.get("maxItems", float("inf"))
        ):
            return False
        if not all(matches(schema.get("items", {}), v) for v in value):
            return False
    if actual == "object":
        if not set(schema.get("required", [])) <= set(value):
            return False
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(props):
            return False
        if not all(matches(props.get(k, {}), v) for k, v in value.items()):
            return False
    return True


def intersect(left: dict, right: dict) -> dict:
    if "anyOf" in left or "anyOf" in right:
        alternatives = []

        def expanded(schema):
            siblings = {k: v for k, v in schema.items() if k != "anyOf"}
            results = []
            for branch in schema.get("anyOf", [{}]):
                try:
                    results.append(intersect(siblings, branch))
                except ValueError:
                    continue
            return results

        for a in expanded(left):
            for b in expanded(right):
                try:
                    alternatives.append(intersect(a, b))
                except ValueError:
                    continue
        if not alternatives:
            raise ValueError("request schemas have no compatible anyOf alternative")
        result = {"anyOf": alternatives}
        for key in ("title", "description", "default"):
            if key in right or key in left:
                result[key] = right.get(key, left.get(key))
        if "default" in result and not matches(result, result["default"]):
            result.pop("default")
        return result
    output = {**left, **right}
    if "format" in left and "format" in right and left["format"] != right["format"]:
        raise ValueError("OpenAPI and Pydantic string formats conflict")

    def types(schema):
        kind = schema.get("type", "object" if "properties" in schema else None)
        values = set(kind if isinstance(kind, list) else [kind] if kind else [])
        if schema.get("nullable"):
            values.add("null")
        return values

    lhs, rhs = types(left), types(right)
    if lhs and rhs:
        compatible = lhs & rhs
        if "integer" in lhs and "number" in rhs or "number" in lhs and "integer" in rhs:
            compatible.add("integer")
        if not compatible:
            raise ValueError("OpenAPI and Pydantic request field types conflict")
        output["type"] = (
            next(iter(compatible)) if len(compatible) == 1 else sorted(compatible)
        )
        output.pop("nullable", None)
    for key in ("minimum", "minLength", "minItems"):
        values = [schema[key] for schema in (left, right) if key in schema]
        if values:
            output[key] = max(values)
    for key in ("maximum", "maxLength", "maxItems"):
        values = [schema[key] for schema in (left, right) if key in schema]
        if values:
            output[key] = min(values)
    for key, inclusive, choose in [
        ("exclusiveMinimum", "minimum", max),
        ("exclusiveMaximum", "maximum", min),
    ]:
        bounds = [
            schema[inclusive] if schema[key] is True else schema[key]
            for schema in (left, right)
            if key in schema
            and schema[key] is not False
            and (schema[key] is not True or inclusive in schema)
        ]
        if bounds:
            output[key] = choose(bounds)
    for low, high in [
        ("minimum", "maximum"),
        ("minLength", "maxLength"),
        ("minItems", "maxItems"),
    ]:
        if low in output and high in output and output[low] > output[high]:
            raise ValueError(f"OpenAPI and Pydantic bounds conflict: {low}/{high}")
    if "enum" in left or "enum" in right:
        pool = left.get("enum", right.get("enum"))
        output["enum"] = [v for v in pool if matches(left, v) and matches(right, v)]
        if not output["enum"]:
            raise ValueError("OpenAPI and Pydantic enums conflict")
    if "const" in left and not matches(right, left["const"]):
        raise ValueError("OpenAPI and Pydantic constants conflict")
    if "const" in right and not matches(left, right["const"]):
        raise ValueError("OpenAPI and Pydantic constants conflict")
    if "properties" in left or "properties" in right:
        props = {**left.get("properties", {}), **right.get("properties", {})}
        for key in (
            left.get("properties", {}).keys() & right.get("properties", {}).keys()
        ):
            props[key] = intersect(left["properties"][key], right["properties"][key])
        output["properties"] = props
        output["required"] = sorted(
            set(left.get("required", [])) | set(right.get("required", []))
        )
    if "items" in left and "items" in right:
        output["items"] = intersect(left["items"], right["items"])
    if (
        left.get("additionalProperties") is False
        or right.get("additionalProperties") is False
    ):
        output["additionalProperties"] = False
        for schema, other in [(left, right), (right, left)]:
            if schema.get("additionalProperties") is False and set(
                other.get("properties", {})
            ) - set(schema.get("properties", {})):
                raise ValueError("OpenAPI and Pydantic object properties conflict")
    if "default" in output and not matches(output, output["default"]):
        output.pop("default")
    return output
