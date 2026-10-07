from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from verisim.fixtures.pipeline import generate_fixtures


def _document(tmp_path: Path):
    api = tmp_path / "api.json"
    api.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/flag": {
                        "post": {
                            "operationId": "setFlag",
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "active": {"type": "boolean"}
                                            },
                                        }
                                    }
                                }
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return api


@pytest.mark.parametrize("output_format", ["json", "csv", "sqlite"])
def test_pipeline_executes_minimizes_replays_and_publishes_portable_bundle(
    tmp_path: Path, output_format: str
):
    api = _document(tmp_path)
    config = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, revision="rev-1", python_paths=[]),
        sources=SimpleNamespace(
            openapi=SimpleNamespace(files=[api]), django=None, pydantic=None
        ),
        operations={
            "setFlag": SimpleNamespace(
                request_model=None, fixture_models=[], fixture_rows={}, bindings={}
            )
        },
        branches=SimpleNamespace(adapter="unused:adapter", options={}),
        execution=SimpleNamespace(runner="unused:runner", options={}),
        generation=SimpleNamespace(
            seed=1, clock="2026-01-01T00:00:00Z", candidate_limit=10, candidates=[]
        ),
        minimization=SimpleNamespace(timeout_seconds=2),
        output=SimpleNamespace(
            format=output_format,
            path=tmp_path / f"fixtures.{output_format}",
            report=tmp_path / "report.json",
        ),
    )

    def provider(*, options, context):
        return {
            "version": 1,
            "source_revision": "rev-1",
            "scope": {"operations": ["setFlag"], "complete": True},
            "targets": [
                {
                    "id": "on",
                    "operation_id": "setFlag",
                    "constraints": [
                        {"path": "request.body.active", "op": "eq", "value": True}
                    ],
                },
                {
                    "id": "off",
                    "operation_id": "setFlag",
                    "constraints": [
                        {"path": "request.body.active", "op": "eq", "value": False}
                    ],
                },
            ],
        }

    def runner(scenario, *, context):
        branch = "on" if scenario["request"]["body"]["active"] else "off"
        return {
            "version": 1,
            "scenario_id": scenario["id"],
            "operation_id": "setFlag",
            "source_revision": "rev-1",
            "input_fingerprint": context["input_fingerprint"],
            "execution_valid": True,
            "coverage_valid": True,
            "measured_invocations": 1,
            "isolated": True,
            "observed_branch_ids": [branch],
            "checks_passed": True,
            "diagnostics": [],
        }

    result = generate_fixtures(config, branch_provider=provider, runner=runner)
    assert result.status == "complete"
    assert (
        result.coverage_complete
        and result.optimal_within_pool
        and result.replay_verified
    )
    assert result.scenario_count == 2
    fixture = Path(result.fixture_path)
    assert result.fixture_sha256 == hashlib.sha256(fixture.read_bytes()).hexdigest()
    if output_format == "json":
        bundle = json.loads(fixture.read_text(encoding="utf-8"))
    else:
        from verisim.fixtures.exporters import read_bundle

        bundle = read_bundle(fixture, output_format)
    assert len(bundle["scenarios"]) == 2
    assert Path(result.report_path).is_file()


def test_pipeline_writes_report_but_no_fixture_when_coverage_is_incomplete(
    tmp_path: Path,
):
    api = _document(tmp_path)
    config = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, revision="rev-1", python_paths=[]),
        sources=SimpleNamespace(
            openapi=SimpleNamespace(files=[api]), django=None, pydantic=None
        ),
        operations={
            "setFlag": SimpleNamespace(
                request_model=None, fixture_models=[], fixture_rows={}, bindings={}
            )
        },
        branches=SimpleNamespace(adapter="unused:adapter", options={}),
        execution=SimpleNamespace(runner="unused:runner", options={}),
        generation=SimpleNamespace(
            seed=1, clock="2026-01-01T00:00:00Z", candidate_limit=1, candidates=[]
        ),
        minimization=SimpleNamespace(timeout_seconds=2),
        output=SimpleNamespace(
            format="json",
            path=tmp_path / "fixtures.json",
            report=tmp_path / "report.json",
        ),
    )

    def provider(**_):
        return {
            "version": 1,
            "source_revision": "rev-1",
            "scope": {"operations": ["setFlag"], "complete": True},
            "targets": [
                {
                    "id": "on",
                    "operation_id": "setFlag",
                    "constraints": [
                        {"path": "request.body.active", "op": "eq", "value": True}
                    ],
                },
                {
                    "id": "off",
                    "operation_id": "setFlag",
                    "constraints": [
                        {"path": "request.body.active", "op": "eq", "value": False}
                    ],
                },
            ],
        }

    def runner(scenario, **_):
        return {
            "version": 1,
            "scenario_id": scenario["id"],
            "operation_id": "setFlag",
            "source_revision": "rev-1",
            "input_fingerprint": "wrong",
            "execution_valid": True,
            "coverage_valid": True,
            "measured_invocations": 1,
            "isolated": True,
            "observed_branch_ids": [],
            "checks_passed": True,
            "diagnostics": [],
        }

    result = generate_fixtures(config, branch_provider=provider, runner=runner)
    assert result.status == "coverage_incomplete"
    assert result.fixture_path is None
    assert Path(result.report_path).exists()
