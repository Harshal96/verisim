from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable


class OptimizationError(ValueError):
    """The scenario optimization problem is invalid."""


@dataclass(frozen=True)
class OptimizationResult:
    selected: tuple[Any, ...]
    optimal_within_pool: bool
    missing_targets: frozenset[str]
    candidate_pool_size: int
    explored_nodes: int
    timed_out: bool


def select_minimum_scenarios(
    candidates: Iterable[Any],
    required_targets: set[str] | frozenset[str],
    execution_results: Any,
    *,
    timeout_seconds: float,
) -> OptimizationResult:
    if not required_targets:
        raise OptimizationError("required target universe cannot be empty")
    if timeout_seconds <= 0:
        raise OptimizationError("timeout_seconds must be positive")
    scenario_map = {scenario.id: scenario for scenario in candidates}
    records = {record.scenario_id: record for record in execution_results.records}
    coverage: dict[str, frozenset[str]] = {}
    for scenario_id, scenario in scenario_map.items():
        record = records.get(scenario_id)
        if record is None or not record.coverage_valid:
            continue
        coverage[scenario_id] = frozenset(record.observed_branch_ids) & required_targets
    coverage = {key: values for key, values in coverage.items() if values}
    covered_universe = (
        frozenset().union(*coverage.values()) if coverage else frozenset()
    )
    missing = frozenset(required_targets) - covered_universe
    if missing:
        return OptimizationResult((), False, missing, len(scenario_map), 0, False)

    ids = sorted(coverage)
    by_target = {
        target: [identifier for identifier in ids if target in coverage[identifier]]
        for target in required_targets
    }
    deadline = time.monotonic() + timeout_seconds
    best: tuple[str, ...] | None = None
    explored = 0
    timed_out = False
    universe = frozenset(required_targets)

    def search(chosen: tuple[str, ...], covered: frozenset[str]) -> None:
        nonlocal best, explored, timed_out
        if time.monotonic() >= deadline:
            timed_out = True
            return
        explored += 1
        if covered >= universe:
            candidate = tuple(sorted(chosen))
            if best is None or (len(candidate), candidate) < (len(best), best):
                best = candidate
            return
        if best is not None and len(chosen) >= len(best):
            return
        remaining = universe - covered
        max_gain = max(
            (len(coverage[item] & remaining) for item in ids if item not in chosen),
            default=0,
        )
        if max_gain == 0:
            return
        lower_bound = (len(remaining) + max_gain - 1) // max_gain
        if best is not None and len(chosen) + lower_bound > len(best):
            return
        # Branch on the uncovered target with the fewest candidate choices.
        target = min(remaining, key=lambda item: (len(by_target[item]), item))
        for identifier in by_target[target]:
            if identifier in chosen:
                continue
            search((*chosen, identifier), covered | coverage[identifier])
            if timed_out:
                return

    search((), frozenset())
    if best is None:
        return OptimizationResult(
            (), False, universe, len(scenario_map), explored, timed_out
        )
    return OptimizationResult(
        tuple(scenario_map[item] for item in best),
        not timed_out,
        (
            frozenset()
            if not timed_out
            else universe - frozenset().union(*(coverage[item] for item in best))
        ),
        len(scenario_map),
        explored,
        timed_out,
    )


__all__ = ["OptimizationError", "OptimizationResult", "select_minimum_scenarios"]
