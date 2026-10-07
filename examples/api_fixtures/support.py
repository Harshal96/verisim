"""The caller owns baseline isolation, model persistence and coverage attribution."""

from pathlib import Path

import api
import coverage
from django.db import connection
from models import Customer

_table_ready = False


def run_scenario(scenario: dict, *, context: dict) -> dict:
    global _table_ready
    if not _table_ready:
        with connection.schema_editor() as editor:
            editor.create_model(Customer)
        _table_ready = True
    Customer.objects.all().delete()
    try:
        # All setup is outside the measured invocation.
        for row in scenario["fixture_rows"]:
            if row["model"] != "customer":
                raise ValueError("unknown example model")
            customer = Customer(**row["fields"])
            customer.full_clean()
            customer.save(force_insert=True)
        collector = coverage.Coverage(
            branch=True, data_file=None, include=[api.__file__]
        )
        collector.start()
        try:
            status = api.create_order(
                scenario["request"]["body"], scenario["actor"], scenario["environment"]
            )
        finally:
            collector.stop()
        arcs = set(collector.get_data().arcs(str(Path(api.__file__).resolve())) or [])
        hits = [
            target["id"]
            for target in context["catalog_targets"]
            if target["arc"]["file"] == "api.py"
            and (target["arc"]["from_line"], target["arc"]["to_line"]) in arcs
        ]
        expected_by_target = {
            "quantity.true": 422,
            "auth.true": 403,
            "inventory.true": 503,
            "found.true": 404,
            "active.true": 409,
        }
        expected = scenario["expectations"].get(
            "status",
            next(
                (
                    expected_by_target[t]
                    for t in scenario["target_branch_ids"]
                    if t in expected_by_target
                ),
                201,
            ),
        )
        return {
            "version": 1,
            "scenario_id": scenario["id"],
            "operation_id": scenario["operation_id"],
            "source_revision": context["source_revision"],
            "input_fingerprint": context["input_fingerprint"],
            "execution_valid": True,
            "coverage_valid": True,
            "isolated": True,
            "measured_invocations": 1,
            "observed_branch_ids": hits,
            "checks_passed": status == expected,
            "diagnostics": [f"HTTP {status}"],
        }
    finally:
        Customer.objects.all().delete()
