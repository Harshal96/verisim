"""Lossless, versioned JSON values shared by all fixture storage formats."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

TAG = "$verisim"


def encode(value: Any) -> Any:
    if isinstance(value, datetime):
        kind, text = "datetime", value.isoformat()
    elif isinstance(value, date):
        kind, text = "date", value.isoformat()
    elif isinstance(value, UUID):
        kind, text = "uuid", str(value)
    elif isinstance(value, Decimal):
        kind, text = "decimal", str(value)
    elif isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("fixture mappings require string keys")
        if TAG in value:
            return {
                TAG: {
                    "type": "mapping",
                    "value": [[k, encode(v)] for k, v in value.items()],
                }
            }
        return {key: encode(item) for key, item in value.items()}
    elif isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    else:
        return value
    return {TAG: {"type": kind, "value": text}}


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) != {TAG}:
        return {key: decode(item) for key, item in value.items()}
    tag = value[TAG]
    if not isinstance(tag, dict) or set(tag) != {"type", "value"}:
        raise ValueError("invalid fixture value tag")
    kind, text = tag["type"], tag["value"]
    if kind == "mapping":
        return {key: decode(item) for key, item in text}
    constructors = {
        "date": date.fromisoformat,
        "datetime": datetime.fromisoformat,
        "uuid": UUID,
        "decimal": Decimal,
    }
    if kind not in constructors or not isinstance(text, str):
        raise ValueError("unknown fixture value tag")
    return constructors[kind](text)
