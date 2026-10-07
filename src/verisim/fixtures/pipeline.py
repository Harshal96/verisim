from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from verisim.fixtures.branches import _resolve, load_catalog
from verisim.fixtures.codec import encode
from verisim.fixtures.exporters import read_bundle, write_bundle
from verisim.fixtures.minimize import select_minimum_scenarios
from verisim.fixtures.provenance import build_provenance, fingerprint
from verisim.fixtures.runner import ExecutionRecord, execute_candidates, resolve_runner
from verisim.fixtures.scenarios import generate_candidates
from verisim.fixtures.sources import FixtureSourceError, _python_paths, load_sources


@dataclass(frozen=True)
class FixtureResult:
    status: str
    run_id: str
    fixture_path: str | None
    report_path: str
    fixture_sha256: str | None
    scenario_count: int
    coverage_complete: bool
    optimal_within_pool: bool
    replay_verified: bool
    checks_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def generate_fixtures(
    config: Any,
    *,
    branch_provider: Callable[..., Any] | None = None,
    runner: Callable[..., Any] | None = None,
) -> FixtureResult:
    """Generate fixtures with project imports active and callback logs on stderr."""
    with (
        _python_paths([config.project.root, *config.project.python_paths]),
        redirect_stdout(sys.stderr),
    ):
        return _generate_fixtures(
            config, branch_provider=branch_provider, runner=runner
        )


def _protect_inputs(config: Any, paths: Any) -> None:
    outputs = {Path(config.output.path).resolve(), Path(config.output.report).resolve()}
    if len(outputs) != 2:
        raise ValueError("fixture and report paths must be different")
    inputs = {Path(p).resolve() for p in paths}
    config_path = getattr(config, "_config_path", None)
    if config_path is not None:
        inputs.add(config_path.resolve())
    if outputs & inputs:
        raise ValueError(
            "fixture and report output paths must not overwrite source inputs"
        )


def _generate_fixtures(
    config: Any, *, branch_provider: Any, runner: Any
) -> FixtureResult:
    """Run the complete candidate, measurement, minimization, replay pipeline."""
    _protect_inputs(config, config.sources.openapi.files)
    run_id = str(uuid.uuid4())
    sources = load_sources(config)
    provider = branch_provider or _resolve(config.branches.adapter)
    catalog = load_catalog(config, sources, provider=provider)
    callback = runner or resolve_runner(config.execution.runner)
    provenance = build_provenance(config, sources, catalog, provider, callback)
    callback_paths = [
        entry["source_path"]
        for entry in (provenance["branch_adapter"], provenance["runner"])
        if entry["source_path"]
    ]
    _protect_inputs(config, [*provenance["source_files"], *callback_paths])
    pool = generate_candidates(config, sources, catalog)
    _assert_source_snapshot(config, sources.input_fingerprint)
    _assert_provenance_snapshot(config, provenance)
    targets_by_operation: dict[str, set[str]] = {
        operation_id: {target.id for target in catalog.targets_for(operation_id)}
        for operation_id in catalog.operations
    }
    catalog_targets = [
        {"id": target.id, "operation_id": target.operation_id, "arc": target.arc}
        for target in catalog.targets
    ]
    executions = execute_candidates(
        pool.scenarios,
        callback,
        source_fingerprint=sources.input_fingerprint,
        source_revision=config.project.revision,
        targets=targets_by_operation,
        options=config.execution.options,
        catalog_targets=catalog_targets,
    )
    required = set(catalog.target_ids)
    covered = (
        set().union(
            *(
                record.observed_branch_ids
                for record in executions.records
                if record.coverage_valid
            )
        )
        if executions.records
        else set()
    )
    missing = required - covered
    optimized = select_minimum_scenarios(
        pool.scenarios,
        required,
        executions,
        timeout_seconds=config.minimization.timeout_seconds,
    )
    coverage_complete = not missing
    optimal = optimized.optimal_within_pool
    replay_verified = False
    replay_results = None
    selected = optimized.selected
    if coverage_complete and optimal and selected:
        replay_results = execute_candidates(
            selected,
            callback,
            source_fingerprint=sources.input_fingerprint,
            source_revision=config.project.revision,
            targets=targets_by_operation,
            options=config.execution.options,
            catalog_targets=catalog_targets,
        )
        original_records = executions.by_scenario_id
        replay_records = replay_results.by_scenario_id
        replay_verified = all(
            scenario.id in original_records
            and scenario.id in replay_records
            and original_records[scenario.id].coverage_valid
            and replay_records[scenario.id].coverage_valid
            and original_records[scenario.id].observed_branch_ids
            == replay_records[scenario.id].observed_branch_ids
            for scenario in selected
        ) and required <= set().union(
            *(
                record.observed_branch_ids
                for record in replay_results.records
                if record.coverage_valid
            )
        )
    selected_original = [executions.by_scenario_id.get(item.id) for item in selected]
    checks_passed = bool(selected) and all(
        record is not None and record.checks_passed for record in selected_original
    )
    if replay_results is not None:
        checks_passed = checks_passed and all(
            record.checks_passed for record in replay_results.records
        )
    _assert_source_snapshot(config, sources.input_fingerprint)
    _assert_provenance_snapshot(config, provenance)

    fixture_path: str | None = None
    fixture_digest: str | None = None
    if not coverage_complete:
        status = "coverage_incomplete"
    elif not optimal:
        status = "optimization_incomplete"
    elif not replay_verified:
        status = "replay_failed"
    else:
        status = "complete" if checks_passed else "checks_failed"

    report: dict[str, Any] = {
        "version": 1,
        "run_id": run_id,
        "status": status,
        "source_revision": config.project.revision,
        "input_fingerprint": sources.input_fingerprint,
        "provenance": provenance,
        "generation_diagnostics": list(pool.diagnostics),
        "scope": {"operations": list(catalog.operations), "complete": True},
        "required_target_ids": sorted(required),
        "covered_target_ids": sorted(covered),
        "missing_target_ids": sorted(missing),
        "candidate_count": len(pool.scenarios),
        "candidate_limit": pool.candidate_limit,
        "candidate_limit_reached": pool.limit_reached,
        "optimization": {
            "optimal_within_pool": optimal,
            "selected_count": len(selected),
            "candidate_pool_size": optimized.candidate_pool_size,
            "explored_nodes": optimized.explored_nodes,
            "timed_out": optimized.timed_out,
        },
        "coverage_complete": coverage_complete,
        "optimal_within_pool": optimal,
        "replay_verified": replay_verified,
        "checks_passed": checks_passed,
        "candidate_receipts": [
            _record_payload(record) for record in executions.records
        ],
        "replay_receipts": (
            []
            if replay_results is None
            else [_record_payload(record) for record in replay_results.records]
        ),
        "fixture_sha256": None,
    }

    bundle: dict[str, Any] | None = None
    if coverage_complete and optimal and replay_verified:
        original_by_id = executions.by_scenario_id
        replay_by_id = replay_results.by_scenario_id if replay_results else {}
        records = []
        for scenario in sorted(selected, key=lambda item: item.id):
            payload = scenario.to_dict()
            payload["receipt"] = original_by_id[scenario.id].receipt
            payload["replay_receipt"] = replay_by_id[scenario.id].receipt
            records.append(payload)
        bundle = {
            "version": 1,
            "run_id": run_id,
            "source_revision": config.project.revision,
            "input_fingerprint": sources.input_fingerprint,
            "provenance": provenance,
            "required_target_ids": sorted(required),
            "scenarios": records,
        }
    report_path = Path(config.output.report).resolve()
    fixture_output = Path(config.output.path).resolve()
    temp_path: Path | None = None
    if bundle is not None:
        try:
            temp_path = _temporary_sibling(fixture_output)
            write_bundle(bundle, temp_path, config.output.format)
            decoded = read_bundle(temp_path, config.output.format)
            if decoded != bundle:
                raise ValueError(
                    "serialized fixture bundle failed round-trip validation"
                )
            fixture_digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
            report["fixture_sha256"] = fixture_digest
        except Exception as error:
            status = "publication_failed"
            report["status"] = status
            report["publication_error"] = f"{error.__class__.__name__}: {error}"
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
                temp_path = None
    try:
        _atomic_json(report_path, report)
    except OSError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        return FixtureResult(
            "publication_failed",
            run_id,
            None,
            str(report_path),
            None,
            0,
            coverage_complete,
            optimal,
            replay_verified,
            checks_passed,
        )
    if bundle is not None and temp_path is not None:
        try:
            os.replace(temp_path, fixture_output)
            fixture_path = str(fixture_output)
        except OSError as error:
            status = "publication_failed"
            report["status"] = status
            report["publication_error"] = f"{error.__class__.__name__}: {error}"
            report["fixture_sha256"] = None
            fixture_digest = None
            try:
                _atomic_json(report_path, report)
            except OSError:
                pass
        finally:
            temp_path.unlink(missing_ok=True)
    return FixtureResult(
        status,
        run_id,
        fixture_path,
        str(report_path),
        fixture_digest,
        len(selected) if fixture_path else 0,
        coverage_complete,
        optimal,
        replay_verified,
        checks_passed,
    )


def _record_payload(record: ExecutionRecord) -> dict[str, Any]:
    return record.receipt


def _assert_source_snapshot(config: Any, expected_fingerprint: str) -> None:
    current = load_sources(config)
    if current.input_fingerprint != expected_fingerprint:
        raise FixtureSourceError(
            "API/model inputs changed during generation; retry with a pinned revision"
        )


def _assert_provenance_snapshot(config: Any, provenance: dict) -> None:
    if fingerprint(config) != provenance["config_fingerprint"]:
        raise FixtureSourceError("configuration changed during generation")
    files = dict(provenance["source_files"])
    for callback in (provenance["branch_adapter"], provenance["runner"]):
        if callback["source_path"]:
            files[callback["source_path"]] = callback["source_sha256"]
    for path, digest in files.items():
        try:
            actual = "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError as error:
            raise FixtureSourceError(f"pinned input disappeared: {path}") from error
        if actual != digest:
            raise FixtureSourceError(f"pinned input changed during generation: {path}")


def _temporary_sibling(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    return Path(name)


def _atomic_json(path: Path, value: Any) -> None:
    temp = _temporary_sibling(path)
    try:
        temp.write_text(
            json.dumps(encode(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


__all__ = ["FixtureResult", "generate_fixtures"]
