from __future__ import annotations

from verisim.fixtures.runner import execute_candidates
from verisim.fixtures.scenarios import Scenario


def _scenario():
    return Scenario(
        "s1",
        "create",
        "rev-1",
        1,
        "2026-01-01T00:00:00Z",
        {"method": "GET"},
        (),
        {},
        {},
        (),
        {},
        ("create.hit",),
    )


def test_runner_receipt_is_validated_and_assertions_are_separate_from_coverage():
    def runner(scenario, *, context):
        return {
            "version": 1,
            "scenario_id": scenario["id"],
            "operation_id": "create",
            "source_revision": "rev-1",
            "input_fingerprint": "fp",
            "execution_valid": True,
            "coverage_valid": True,
            "measured_invocations": 1,
            "isolated": True,
            "observed_branch_ids": ["create.hit"],
            "checks_passed": False,
            "diagnostics": ["unexpected status"],
        }

    result = execute_candidates(
        [_scenario()],
        runner,
        source_fingerprint="fp",
        targets={"create": {"create.hit"}},
        source_revision="rev-1",
    )
    assert result.records[0].coverage_valid
    assert result.records[0].observed_branch_ids == frozenset({"create.hit"})
    assert not result.records[0].checks_passed


def test_malformed_receipt_does_not_contribute_coverage():
    def runner(scenario, *, context):
        return {
            "version": 1,
            "scenario_id": "wrong",
            "operation_id": "create",
            "source_revision": "rev-1",
            "input_fingerprint": "fp",
            "execution_valid": True,
            "coverage_valid": True,
            "measured_invocations": 2,
            "isolated": False,
            "observed_branch_ids": ["other.hit"],
            "checks_passed": True,
        }

    result = execute_candidates(
        [_scenario()],
        runner,
        source_fingerprint="fp",
        targets={"create": {"create.hit"}},
        source_revision="rev-1",
    )
    assert not result.records[0].coverage_valid
    assert result.records[0].observed_branch_ids == frozenset()
    assert result.records[0].diagnostics
