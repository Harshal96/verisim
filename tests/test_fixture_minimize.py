from __future__ import annotations

from types import SimpleNamespace

from verisim.fixtures.minimize import select_minimum_scenarios


def _candidate(identifier: str):
    return SimpleNamespace(id=identifier, operation_id="op")


def _record(identifier: str, observed: set[str]):
    return SimpleNamespace(
        scenario_id=identifier,
        coverage_valid=True,
        observed_branch_ids=frozenset(observed),
    )


def test_selects_exact_minimum_where_greedy_needs_three_scenarios():
    candidates = [_candidate("a"), _candidate("b"), _candidate("c"), _candidate("d")]
    receipts = SimpleNamespace(
        records=(
            _record("a", {"1", "2", "3"}),
            _record("b", {"1", "4"}),
            _record("c", {"2", "5"}),
            _record("d", {"3", "6"}),
        )
    )
    result = select_minimum_scenarios(
        candidates, {"1", "2", "3", "4", "5", "6"}, receipts, timeout_seconds=1
    )
    assert result.optimal_within_pool is True
    assert {item.id for item in result.selected} == {"b", "c", "d"}


def test_reports_missing_targets_without_claiming_optimality():
    result = select_minimum_scenarios(
        [_candidate("a")],
        {"required"},
        SimpleNamespace(records=(_record("a", set()),)),
        timeout_seconds=1,
    )
    assert result.optimal_within_pool is False
    assert result.missing_targets == frozenset({"required"})
    assert result.selected == ()


def test_tied_optima_use_canonical_scenario_id_order():
    candidates = [_candidate("z-scenario"), _candidate("a-scenario")]
    receipts = SimpleNamespace(
        records=(
            _record("z-scenario", {"one"}),
            _record("a-scenario", {"one"}),
        )
    )
    result = select_minimum_scenarios(candidates, {"one"}, receipts, timeout_seconds=1)
    assert [scenario.id for scenario in result.selected] == ["a-scenario"]


def test_zero_target_universe_is_rejected():
    import pytest

    from verisim.fixtures.minimize import OptimizationError

    with pytest.raises(OptimizationError, match="empty"):
        select_minimum_scenarios(
            [], set(), SimpleNamespace(records=()), timeout_seconds=1
        )
