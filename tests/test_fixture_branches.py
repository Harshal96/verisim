from __future__ import annotations

import pytest

from verisim.fixtures.branches import BranchCatalogError, load_catalog
from verisim.fixtures.constraints import ConstraintError, evaluate


def _sources():
    from types import SimpleNamespace

    return SimpleNamespace(
        operations={"create": object()},
        input_fingerprint="sha256:inputs",
        files=(),
    )


def _catalog(**overrides):
    result = {
        "version": 1,
        "source_revision": "rev-1",
        "scope": {"operations": ["create"], "complete": True},
        "targets": [
            {
                "id": "create.yes",
                "operation_id": "create",
                "constraints": [
                    {"path": "request.body.active", "op": "eq", "value": True}
                ],
            },
            {
                "id": "create.no",
                "operation_id": "create",
                "constraints": [
                    {"path": "request.body.active", "op": "eq", "value": False}
                ],
            },
        ],
    }
    result.update(overrides)
    return result


def _config(adapter: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        project=SimpleNamespace(root="/project", revision="rev-1"),
        operations={"create": object()},
        branches=SimpleNamespace(adapter=adapter, options={}),
    )


def test_load_catalog_validates_complete_scope_revision_and_unique_targets():
    catalog = load_catalog(
        _config("test_fixture_branches:catalog"),
        _sources(),
        provider=lambda **_: _catalog(),
    )
    assert catalog.target_ids == frozenset({"create.yes", "create.no"})

    with pytest.raises(BranchCatalogError, match="revision"):
        load_catalog(
            _config("test_fixture_branches:catalog"),
            _sources(),
            provider=lambda **_: _catalog(source_revision="old"),
        )
    with pytest.raises(BranchCatalogError, match="scope"):
        load_catalog(
            _config("test_fixture_branches:catalog"),
            _sources(),
            provider=lambda **_: _catalog(scope={"operations": [], "complete": True}),
        )
    with pytest.raises(BranchCatalogError, match="duplicate"):
        load_catalog(
            _config("test_fixture_branches:catalog"),
            _sources(),
            provider=lambda **_: _catalog(targets=[_catalog()["targets"][0]] * 2),
        )


def test_constraints_support_nested_logic_and_missing_versus_null():
    scenario = {"request": {"body": {"active": True, "optional": None}}}
    assert evaluate(
        {
            "all": [
                {"path": "request.body.active", "op": "eq", "value": True},
                {
                    "any": [
                        {
                            "path": "request.body.optional",
                            "op": "exists",
                            "value": True,
                        },
                        {
                            "path": "request.body.missing",
                            "op": "exists",
                            "value": False,
                        },
                    ]
                },
            ]
        },
        scenario,
    )
    assert not evaluate(
        {"path": "request.body.missing", "op": "eq", "value": None}, scenario
    )
    assert evaluate(
        {"path": "request.body.optional", "op": "eq", "value": None}, scenario
    )


def test_constraints_validate_operators_numeric_values_and_path_syntax():
    with pytest.raises(ConstraintError, match="operator"):
        evaluate({"path": "request.body.x", "op": "exec", "value": 1}, {})
    with pytest.raises(ConstraintError, match="numeric"):
        evaluate(
            {"path": "request.body.x", "op": "gt", "value": 1},
            {"request": {"body": {"x": "1"}}},
        )
    with pytest.raises(ConstraintError, match="path"):
        evaluate({"path": "unknown.secret", "op": "exists", "value": True}, {})


def test_load_catalog_invokes_generic_callback_with_read_only_context():
    received = {}

    def provider(*, options, context):
        received.update(options=options, context=context)
        return _catalog()

    config = _config("unused:adapter")
    config.branches.options = {"endpoint": "https://graph.invalid"}
    catalog = load_catalog(config, _sources(), provider=provider)
    assert catalog.source_revision == "rev-1"
    assert received["context"]["selected_operations"] == ("create",)
    assert received["context"]["input_fingerprint"] == "sha256:inputs"
