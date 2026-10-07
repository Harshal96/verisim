from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError


def _loader():
    try:
        module = importlib.import_module("verisim.fixtures.config")
    except ModuleNotFoundError as error:
        if error.name in {"verisim.fixtures", "verisim.fixtures.config"}:
            pytest.fail("the fixture configuration loader has not been implemented")
        raise
    return module.load_config, module.FixtureConfigError


def _config() -> dict[str, object]:
    return {
        "version": 1,
        "project": {
            "root": "./service",
            "python_paths": ["src"],
            "revision": "${SOURCE_REVISION}",
        },
        "sources": {
            "openapi": {"files": ["contracts/openapi.json"]},
            "django": {
                "settings_module": "shop.settings.test",
                "models": {"customer": "shop.models:Customer"},
            },
            "pydantic": {"models": {"create_order": "shop.schemas:CreateOrder"}},
        },
        "operations": {
            "createOrder": {
                "request_model": "create_order",
                "fixture_models": ["customer"],
                "bindings": {"request.body.customer_id": "fixtures.customer.id"},
            }
        },
        "branches": {
            "adapter": "company.catalog:load_branches",
            "options": {
                "endpoint": "${KNOWLEDGE_GRAPH_URL}",
                "token_env": "KNOWLEDGE_GRAPH_TOKEN",
            },
        },
        "execution": {"runner": "company.runner:run_scenario"},
        "generation": {
            "seed": 42,
            "clock": "2026-10-07T00:00:00Z",
            "candidate_limit": 500,
        },
        "minimization": {
            "unit": "scenario",
            "method": "exact_set_cover",
            "require_full_coverage": True,
            "timeout_seconds": 30,
        },
        "output": {
            "format": "json",
            "path": "./out/fixtures.json",
            "report": "./out/coverage.json",
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_json_config_resolves_paths_and_expands_only_marked_values(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "fixture-config.json"
    _write_json(config_path, _config())

    load_config, _ = _loader()
    config = load_config(
        config_path,
        environ={
            "SOURCE_REVISION": "abc123",
            "KNOWLEDGE_GRAPH_URL": "https://graph.example.invalid",
            "KNOWLEDGE_GRAPH_TOKEN": "secret-placeholder",
        },
    )

    assert config.project.root == (tmp_path / "service").resolve()
    assert config.project.revision == "abc123"
    assert config.project.python_paths == [(tmp_path / "service/src").resolve()]
    assert config.sources.openapi.files == [
        (tmp_path / "service/contracts/openapi.json").resolve()
    ]
    assert config.branches.options["endpoint"] == "https://graph.example.invalid"
    assert config.branches.options["token_env"] == "KNOWLEDGE_GRAPH_TOKEN"
    assert config.output.path == (tmp_path / "service/out/fixtures.json").resolve()


def test_load_yaml_example_uses_same_config_contract(tmp_path: Path) -> None:
    pytest.importorskip("yaml", reason="install the optional fixtures extra")
    example = Path(__file__).parents[1] / "docs/examples/fixtures/fixtures.yaml"
    load_config, _ = _loader()
    config = load_config(
        example,
        environ={
            "SOURCE_REVISION": "demo-revision",
            "KNOWLEDGE_GRAPH_URL": "https://graph.example.invalid",
        },
    )

    assert config.operations["createOrder"].fixture_models == ["customer"]
    assert config.minimization.require_full_coverage is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(unexpected=True),
        lambda payload: payload["minimization"].update(require_full_coverage=False),
        lambda payload: payload["operations"]["createOrder"].update(
            missing_model="Customer"
        ),
        lambda payload: payload["sources"]["pydantic"]["models"].update(
            customer="shop.schemas:Customer"
        ),
    ],
)
def test_load_json_config_rejects_unknown_or_unsafe_contract_values(
    tmp_path: Path, mutate
) -> None:
    payload = _config()
    mutate(payload)
    config_path = tmp_path / "bad-config.json"
    _write_json(config_path, payload)

    load_config, errors = _loader()
    with pytest.raises((errors, ValidationError)):
        load_config(
            config_path,
            environ={
                "SOURCE_REVISION": "abc123",
                "KNOWLEDGE_GRAPH_URL": "https://graph.example.invalid",
            },
        )


def test_load_json_config_fails_before_callbacks_when_env_is_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "missing-env.json"
    _write_json(config_path, _config())

    load_config, errors = _loader()
    with pytest.raises(errors, match="SOURCE_REVISION"):
        load_config(config_path, environ={})


def test_yaml_loader_reports_optional_extra_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    config_path = tmp_path / "fixture-config.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")
    original_import = builtins.__import__

    def without_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("blocked for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_yaml)
    load_config, errors = _loader()
    with pytest.raises(errors, match=r"verisim\[fixtures\]"):
        load_config(config_path, environ={})
