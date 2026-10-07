from __future__ import annotations

from pathlib import Path

from verisim.fixtures.exporters import read_bundle, write_bundle


def _bundle():
    return {
        "version": 1,
        "run_id": "run-1",
        "input_fingerprint": "sha256:inputs",
        "source_revision": "rev-1",
        "required_target_ids": ["b1"],
        "scenarios": [
            {
                "version": 1,
                "id": "s1",
                "operation_id": "create",
                "request": {"body": {"x": None}},
                "fixture_rows": [],
                "receipt": {"observed_branch_ids": ["b1"]},
            }
        ],
    }


def test_json_csv_and_sqlite_roundtrip_logical_bundle(tmp_path: Path):
    for format_name, suffix in (("json", "json"), ("csv", "csv"), ("sqlite", "sqlite")):
        path = tmp_path / f"fixtures.{suffix}"
        write_bundle(_bundle(), path, format_name)
        read = read_bundle(path, format_name)
        assert read == _bundle()
