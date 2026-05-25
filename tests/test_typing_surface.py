from __future__ import annotations

import inspect
from importlib.resources import files
from typing import get_overloads

from verisim import (
    FieldPlan,
    PersonRecord,
    ProviderPlan,
    Verisim,
    export_json_schema,
    infer_providers,
)


def test_package_declares_inline_typing():
    assert files("verisim").joinpath("py.typed").is_file()


def test_public_dx_helpers_are_exported():
    plan = infer_providers(PersonRecord)
    schema = export_json_schema(PersonRecord)

    assert isinstance(plan, ProviderPlan)
    assert isinstance(plan.field("person"), FieldPlan)
    assert schema["title"] == "PersonRecord"


def test_generate_has_overloads_for_explain_mode():
    overloads = get_overloads(Verisim.generate)

    assert overloads
    assert "mode" in inspect.signature(Verisim.generate).parameters
