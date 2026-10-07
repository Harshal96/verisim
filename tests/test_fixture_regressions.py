from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as N
from uuid import UUID

import pytest
from pydantic import BaseModel

from verisim.fixtures.config import load_config
from verisim.fixtures.constraints import evaluate
from verisim.fixtures.exporters import read_bundle, write_bundle
from verisim.fixtures.pipeline import generate_fixtures
from verisim.fixtures.scenarios import _make_value, generate_candidates
from verisim.fixtures.sources import load_sources


@pytest.fixture
def project(tmp_path):
    api = tmp_path / "api.json"
    api.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/flag": {
                        "post": {
                            "operationId": "flag",
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["flag"],
                                            "properties": {"flag": {"type": "boolean"}},
                                        }
                                    }
                                }
                            },
                        }
                    }
                },
            }
        )
    )
    module = "support_" + tmp_path.name.replace("-", "_")
    (tmp_path / f"{module}.py").write_text("""
calls = 0
def catalog(*, options, context):
    print("catalog log")
    return {"version": 1, "source_revision": context["source_revision"],
            "scope": {"complete": True, "operations": ["flag"]},
            "targets": [{"id": "hit", "operation_id": "flag", "constraints": []}]}
def runner(scenario, *, context):
    global calls
    calls += 1
    print("runner log")
    mode = context["options"].get("mode")
    hits = [] if mode == "missing" or (mode == "drift" and calls > 1) else ["hit"]
    return {"version": 1, "scenario_id": scenario["id"],
            "operation_id": scenario["operation_id"],
            "source_revision": context["source_revision"],
            "input_fingerprint": context["input_fingerprint"],
            "execution_valid": True, "coverage_valid": True,
            "isolated": True, "measured_invocations": 1,
            "observed_branch_ids": hits, "checks_passed": mode != "checks",
            "diagnostics": []}
""")
    payload = {
        "version": 1,
        "project": {"root": str(tmp_path), "revision": "rev"},
        "sources": {"openapi": {"files": ["api.json"]}},
        "operations": {"flag": {}},
        "branches": {"adapter": f"{module}:catalog"},
        "execution": {"runner": f"{module}:runner"},
        "generation": {
            "seed": 1,
            "clock": "2026-10-07T00:00:00Z",
            "candidate_limit": 20,
        },
        "minimization": {
            "unit": "scenario",
            "method": "exact_set_cover",
            "require_full_coverage": True,
            "timeout_seconds": 2,
        },
        "output": {"format": "json", "path": "fixtures.json", "report": "report.json"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    return path, payload


@pytest.mark.parametrize("destination", ["config.json", "sub/../api.json"])
def test_outputs_cannot_replace_config_or_normalized_source(project, destination):
    path, _ = project
    config = load_config(path)
    target = path.parent / destination
    before = target.resolve().read_bytes()
    config = config.model_copy(
        update={"output": config.output.model_copy(update={"path": target})}
    )
    with pytest.raises(ValueError, match="overwrite"):
        generate_fixtures(config)
    assert target.resolve().read_bytes() == before


def test_local_callbacks_and_replay_provenance(project):
    path, _ = project
    result = generate_fixtures(load_config(path))
    assert result.status == "complete"
    bundle = read_bundle(result.fixture_path, "json")
    provenance = bundle["provenance"]
    assert provenance["config"]["generation"]["clock"] == "2026-10-07T00:00:00Z"
    assert provenance["catalog"]["targets"][0]["id"] == "hit"
    assert provenance["runner"]["source_sha256"].startswith("sha256:")
    assert provenance["library"]["version"]
    assert provenance["data_pack_fingerprint"].startswith("sha256:")
    assert provenance["config_fingerprint"].startswith("sha256:")


def test_output_cannot_replace_imported_callback(project):
    path, payload = project
    payload["output"]["path"] = payload["execution"]["runner"].split(":")[0] + ".py"
    path.write_text(json.dumps(payload))
    before = (path.parent / payload["output"]["path"]).read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        generate_fixtures(load_config(path))
    assert (path.parent / payload["output"]["path"]).read_bytes() == before


def test_report_publication_failure_preserves_old_fixture(project):
    path, payload = project
    (path.parent / "fixtures.json").write_text("old fixture")
    (path.parent / "report-dir").mkdir()
    payload["output"]["report"] = "report-dir"
    path.write_text(json.dumps(payload))
    result = generate_fixtures(load_config(path))
    assert result.status == "publication_failed"
    assert result.fixture_path is None and result.fixture_sha256 is None
    assert (path.parent / "fixtures.json").read_text() == "old fixture"
    assert not list(path.parent.glob("*.tmp"))


def test_optimization_timeout_process_exit(project):
    path, payload = project
    payload["minimization"]["timeout_seconds"] = 1e-30
    path.write_text(json.dumps(payload))
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "verisim.cli", "fixtures", "--config", str(path)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 3
    assert json.loads(completed.stdout)["status"] == "optimization_incomplete"


@pytest.mark.parametrize(
    "mode,code,status",
    [
        (None, 0, "complete"),
        ("checks", 4, "checks_failed"),
        ("missing", 3, "coverage_incomplete"),
        ("drift", 3, "replay_failed"),
        ("publication", 5, "publication_failed"),
    ],
)
def test_process_manifest_logging_and_exit_codes(project, mode, code, status):
    path, payload = project
    payload["execution"]["options"] = {"mode": mode}
    if mode == "publication":
        (path.parent / "destination").mkdir()
        payload["output"]["path"] = "destination"
    path.write_text(json.dumps(payload))
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "verisim.cli", "fixtures", "--config", str(path)],
        capture_output=True,
        text=True,
        cwd=path.parent,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
    )
    assert completed.returncode == code, completed.stderr
    manifest = json.loads(completed.stdout)
    assert manifest["status"] == status
    assert "catalog log" in completed.stderr and "runner log" in completed.stderr


def candidate_inputs(expressions, *, rows=None, schema=None):
    op = N(
        request_model=None,
        fixture_models=list((rows or {}).values()),
        fixture_rows=rows or {},
        bindings={},
    )
    config = N(
        project=N(revision="rev"),
        operations={"flag": op},
        generation=N(
            seed=1, clock="2026-10-07T00:00:00Z", candidate_limit=20, candidates=[]
        ),
    )
    sources = N(
        operations={
            "flag": N(method="POST", path="/flag", parameters=(), request_schema=schema)
        },
        model_classes={},
        model_schemas={
            alias: {"type": "object", "properties": {}}
            for alias in (rows or {}).values()
        },
    )
    catalog = N(
        targets=(N(id="hit", operation_id="flag", constraints=tuple(expressions)),)
    )
    return config, sources, catalog


def test_actor_environment_and_array_hints_survive():
    expressions = [
        {"path": "actor.admin", "op": "eq", "value": True},
        {"path": "environment.online", "op": "eq", "value": False},
        {"path": "request.body.items.0", "op": "eq", "value": 42},
    ]
    schema = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {"type": "array", "minItems": 1, "items": {"type": "integer"}}
        },
    }
    scenario = generate_candidates(
        *candidate_inputs(expressions, schema=schema)
    ).scenarios[0]
    assert scenario.actor == {"admin": True}
    assert scenario.environment == {"online": False}
    assert scenario.request["body"]["items"] == [42]


@pytest.mark.parametrize(
    "expression",
    [
        {"not": {"path": "request.body.flag", "op": "eq", "value": False}},
        {"path": "request.body.flag", "op": "ne", "value": False},
        {"path": "request.body.flag", "op": "not_in", "value": [False]},
        {"any": [{"path": "request.body.flag", "op": "ne", "value": False}]},
        {
            "all": [
                {"path": "request.body.x", "op": "gt", "value": 0.1},
                {"path": "request.body.x", "op": "lt", "value": 0.2},
            ]
        },
    ],
)
def test_supported_constraints_construct_a_satisfying_candidate(expression):
    inputs = candidate_inputs(
        [expression],
        schema={
            "type": "object",
            "required": ["flag"],
            "properties": {"flag": {"type": "boolean"}},
        },
    )
    scenario = generate_candidates(*inputs).scenarios[0]
    assert evaluate(
        expression,
        {
            "request": scenario.request,
            "actor": scenario.actor,
            "environment": scenario.environment,
            "fixtures": {},
        },
    )


def test_unsatisfiable_hints_are_reported_instead_of_silently_ignored():
    expressions = [
        {"path": "actor.admin", "op": "eq", "value": True},
        {"path": "actor.admin", "op": "eq", "value": False},
    ]
    pool = generate_candidates(*candidate_inputs(expressions))
    assert not pool.scenarios
    assert pool.diagnostics[0]["target_branch_ids"] == ["hit"]
    assert "satisf" in pool.diagnostics[0]["reason"]


def test_absent_fixture_row_is_removed():
    pool = generate_candidates(
        *candidate_inputs(
            [{"path": "fixtures.person", "op": "exists", "value": False}],
            rows={"person": "user"},
        )
    )
    assert pool.scenarios[0].fixture_rows == ()


def test_absent_row_keeps_request_id_when_binding_origin_disappears():
    config, sources, catalog = candidate_inputs(
        [{"path": "fixtures.person", "op": "exists", "value": False}],
        rows={"person": "user"},
        schema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer"}},
        },
    )
    config.operations["flag"].bindings = {"request.body.id": "fixtures.person.id"}
    pool = generate_candidates(config, sources, catalog)
    assert pool.scenarios, pool.diagnostics
    assert pool.scenarios[0].fixture_rows == ()
    assert pool.scenarios[0].request["body"]["id"] == 1


def test_json_fields_with_ref_keys_remain_scalar_fields(project):
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=[],
            DATABASES={
                "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
            },
        )
        django.setup()
    from django.db import models

    class JsonRecord(models.Model):
        payload = models.JSONField(default=dict)

        class Meta:
            app_label = "fixture_json_regression"

    path, payload = project
    payload["sources"]["django"] = {
        "settings_module": "unused",
        "models": {"record": "unused:Record"},
    }
    payload["operations"]["flag"] = {"fixture_models": ["record"]}
    payload["generation"]["candidates"] = [
        {
            "operation_id": "flag",
            "values": {"fixtures.record.payload": {"$ref": "literal"}},
        }
    ]
    path.write_text(json.dumps(payload))
    config = load_config(path)
    sources = load_sources(config, model_overrides={"record": JsonRecord})
    pool = generate_candidates(config, sources, N(targets=()))
    populated = next(
        s for s in pool.scenarios if s.fixture_rows[0]["fields"].get("payload")
    )
    assert populated.fixture_rows[0]["fields"]["payload"] == {"$ref": "literal"}
    assert populated.fixture_rows[0]["relations"] == {}


def test_candidate_identity_and_dedup_are_independent_of_catalog_order():
    config, sources, catalog = candidate_inputs([])
    catalog.targets = (
        N(id="a", operation_id="flag", constraints=()),
        N(id="b", operation_id="flag", constraints=()),
    )
    first = generate_candidates(config, sources, catalog)
    catalog.targets = tuple(reversed(catalog.targets))
    second = generate_candidates(config, sources, catalog)
    assert first.scenarios == second.scenarios
    assert len(first.scenarios) == 1
    assert first.scenarios[0].target_branch_ids == ("a", "b")


def test_binding_conflicts_are_diagnosed():
    inputs = candidate_inputs([], schema={"type": "object"})
    config, sources, catalog = inputs
    config.operations["flag"].bindings = {"request.body.id": "actor.id"}
    config.generation.candidates = [
        N(
            operation_id="flag",
            values={"request.body.id": 1, "actor.id": 2},
            expectations={},
        )
    ]
    pool = generate_candidates(*inputs)
    assert any("binding conflict" in d["reason"] for d in pool.diagnostics)


def test_file_catalog_adapter_resolves_project_path(project):
    path, payload = project
    (path.parent / "catalog.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source_revision": "rev",
                "scope": {"complete": True, "operations": ["flag"]},
                "targets": [{"id": "hit", "operation_id": "flag", "constraints": []}],
            }
        )
    )
    payload["branches"] = {
        "adapter": "verisim.fixtures.adapters.file:load_branches",
        "options": {"path": "catalog.json"},
    }
    path.write_text(json.dumps(payload))
    assert generate_fixtures(load_config(path)).status == "complete"


@pytest.mark.parametrize("format", ["json", "csv", "sqlite"])
def test_runnable_django_example_measures_and_replays_real_arcs(tmp_path, format):
    root = Path(__file__).resolve().parents[1]
    example = root / "examples" / "api_fixtures"
    payload = json.loads((example / "fixtures.json").read_text())
    payload["project"]["root"] = str(example)
    payload["output"] = {
        "format": format,
        "path": str(tmp_path / f"fixtures.{format}"),
        "report": str(tmp_path / "report.json"),
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    process = subprocess.run(
        [sys.executable, "-B", "-m", "verisim.cli", "fixtures", "--config", str(path)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    manifest = json.loads(process.stdout)
    assert manifest["scenario_count"] == 6
    assert (
        manifest["coverage_complete"]
        and manifest["optimal_within_pool"]
        and manifest["replay_verified"]
    )
    bundle = read_bundle(manifest["fixture_path"], format)
    assert {s["receipt"]["diagnostics"][0] for s in bundle["scenarios"]} == {
        "HTTP 201",
        "HTTP 403",
        "HTTP 404",
        "HTTP 409",
        "HTTP 422",
        "HTTP 503",
    }


@pytest.mark.parametrize(
    "schema,want",
    [
        ({"type": "integer", "maximum": 0}, 0),
        ({"type": "integer", "minimum": 0.5}, 1),
        ({"type": "string", "maxLength": 0}, ""),
    ],
)
def test_valid_schema_boundaries(schema, want):
    assert _make_value(schema, random.Random(1)) == want


class NullablePayload(BaseModel):
    name: str | None = None


class AmountPayload(BaseModel):
    amount: int = 1


def test_pydantic_and_openapi_constraints_both_apply(project):
    path, payload = project
    api_path = path.parent / "api.json"
    api = json.loads(api_path.read_text())
    schema = api["paths"]["/flag"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    schema.update(
        {
            "required": ["amount"],
            "properties": {"amount": {"type": "integer", "minimum": 10}},
        }
    )
    api_path.write_text(json.dumps(api))
    payload["sources"]["pydantic"] = {"models": {"request": "unused:Payload"}}
    payload["operations"]["flag"]["request_model"] = "request"
    path.write_text(json.dumps(payload))
    config = load_config(path)
    sources = load_sources(config, model_overrides={"request": AmountPayload})
    pool = generate_candidates(config, sources, N(targets=()))
    assert pool.scenarios[0].request["body"]["amount"] == 10


def test_conflicting_request_model_types_fail_source_loading(project):
    from verisim.fixtures.sources import FixtureSourceError

    path, payload = project
    api_path = path.parent / "api.json"
    api = json.loads(api_path.read_text())
    api["paths"]["/flag"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ] = {"type": "object", "properties": {"amount": {"type": "string"}}}
    api_path.write_text(json.dumps(api))
    payload["sources"]["pydantic"] = {"models": {"request": "unused:Payload"}}
    payload["operations"]["flag"]["request_model"] = "request"
    path.write_text(json.dumps(payload))
    with pytest.raises(FixtureSourceError, match="types conflict"):
        load_sources(load_config(path), model_overrides={"request": AmountPayload})


@pytest.mark.parametrize(
    "schema,want",
    [
        ({"type": "integer", "minimum": 10, "exclusiveMinimum": 0}, 10),
        ({"type": "integer", "maximum": 0, "exclusiveMaximum": 10}, 0),
        ({"type": "number", "minimum": 10, "exclusiveMinimum": 0.0}, 10.0),
    ],
)
def test_inclusive_and_exclusive_bounds_are_intersected(schema, want):
    assert _make_value(schema, random.Random(1)) == want


@pytest.mark.parametrize(
    "schema,want",
    [
        ({"type": "integer", "minimum": 10.5, "exclusiveMinimum": 0}, 11),
        ({"type": "integer", "maximum": 0.5, "exclusiveMaximum": 10}, 0),
        ({"type": "integer", "minimum": 10.5, "exclusiveMinimum": True}, 11),
        ({"type": "integer", "maximum": 0.5, "exclusiveMaximum": True}, 0),
        ({"anyOf": [{"type": "integer"}], "minimum": 10}, 10),
    ],
)
def test_fractional_bounds_and_anyof_siblings(schema, want):
    assert _make_value(schema, random.Random(1)) == want


def test_anyof_intersection_rejects_conflicting_sibling_bounds():
    from verisim.fixtures.schema import intersect

    with pytest.raises(ValueError, match="compatible"):
        intersect(
            {"anyOf": [{"type": "integer"}], "minimum": 10},
            {"type": "integer", "maximum": 5},
        )


@pytest.mark.parametrize("format", ["json", "csv", "sqlite"])
def test_bundle_formats_preserve_scenario_order(tmp_path, format):
    bundle = {
        "version": 1,
        "run_id": "run",
        "input_fingerprint": "fp",
        "scenarios": [
            {"id": "z", "operation_id": "op"},
            {"id": "a", "operation_id": "op"},
        ],
    }
    output = tmp_path / f"bundle.{format}"
    write_bundle(bundle, output, format)
    assert read_bundle(output, format) == bundle


def test_nullable_pydantic_sources(project):
    path, payload = project
    payload["sources"]["pydantic"] = {"models": {"request": "unused:Payload"}}
    payload["operations"]["flag"]["request_model"] = "request"
    path.write_text(json.dumps(payload))
    sources = load_sources(
        load_config(path), model_overrides={"request": NullablePayload}
    )
    assert "anyOf" in sources.model_schemas["request"]["properties"]["name"]


def test_all_django_models_load_and_rows_have_unique_keys(project):
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=[],
            DATABASES={
                "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
            },
        )
        django.setup()
    from django.db import models

    class Team(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "fixture_regressions"

    class Person(models.Model):
        email = models.EmailField()
        birthday = models.DateField()

        class Meta:
            app_label = "fixture_regressions"

    path, payload = project
    payload["sources"]["django"] = {
        "settings_module": "unused",
        "models": {"team": "unused:Team", "person": "unused:Person"},
    }
    payload["operations"]["flag"] = {
        "fixture_models": ["team", "person"],
        "fixture_rows": {"team1": "team", "person1": "person", "person2": "person"},
    }
    path.write_text(json.dumps(payload))
    config = load_config(path)
    sources = load_sources(config, model_overrides={"team": Team, "person": Person})
    assert set(sources.model_schemas) == {"team", "person"}
    pool = generate_candidates(
        config, sources, N(targets=(N(id="hit", operation_id="flag", constraints=()),))
    )
    assert pool.scenarios, pool.diagnostics
    scenario = pool.scenarios[0]
    rows = {r["ref"]: r for r in scenario.fixture_rows}
    assert rows["team1"]["fields"]["name"]
    assert rows["person1"]["fields"]["id"] != rows["person2"]["fields"]["id"]
    assert rows["person1"]["fields"]["birthday"] == date(2026, 10, 7)
    for row in (rows["person1"], rows["person2"]):
        Person(**row["fields"]).full_clean(
            validate_unique=False, validate_constraints=False
        )


@pytest.mark.parametrize("format", ["json", "csv", "sqlite"])
def test_typed_bundle_round_trips_without_losing_types(tmp_path, format):
    values = {
        "date": date(2026, 10, 7),
        "datetime": datetime(2026, 10, 7, tzinfo=timezone.utc),
        "uuid": UUID("00000000-0000-4000-8000-000000000001"),
        "decimal": Decimal("1.2300"),
        "literal": {"$verisim": {"type": "date", "value": "2026-10-07"}},
    }
    bundle = {
        "version": 1,
        "run_id": "run",
        "input_fingerprint": "fp",
        "scenarios": [
            {
                "id": "one",
                "operation_id": "flag",
                "fixture_rows": [{"ref": "row", "fields": values}],
            }
        ],
    }
    output = tmp_path / f"bundle.{format}"
    write_bundle(bundle, output, format)
    assert read_bundle(output, format) == bundle
