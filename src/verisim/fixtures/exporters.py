from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from verisim.fixtures.codec import decode, encode


class FixtureExportError(ValueError):
    """A portable fixture bundle is malformed or unreadable."""


def write_bundle(bundle: dict[str, Any], path: Path | str, format: str) -> Path:
    bundle = encode(bundle)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "json":
        path.write_text(
            json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    elif format == "csv":
        metadata = {key: value for key, value in bundle.items() if key != "scenarios"}
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "version",
                    "run_id",
                    "input_fingerprint",
                    "bundle_metadata_json",
                    "scenario_json",
                ],
            )
            writer.writeheader()
            for scenario in bundle.get("scenarios", []):
                writer.writerow(
                    {
                        "version": bundle["version"],
                        "run_id": bundle["run_id"],
                        "input_fingerprint": bundle["input_fingerprint"],
                        "bundle_metadata_json": json.dumps(
                            metadata, sort_keys=True, separators=(",", ":")
                        ),
                        "scenario_json": json.dumps(
                            scenario, sort_keys=True, separators=(",", ":")
                        ),
                    }
                )
    elif format == "sqlite":
        with sqlite3.connect(path) as connection:
            connection.executescript("""
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE scenarios (
                    id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    position INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                );
            """)
            for key, value in bundle.items():
                if key == "scenarios":
                    continue
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    (key, json.dumps(value, sort_keys=True, separators=(",", ":"))),
                )
            for position, scenario in enumerate(bundle.get("scenarios", [])):
                connection.execute(
                    "INSERT INTO scenarios(id, operation_id, position, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        scenario["id"],
                        scenario["operation_id"],
                        position,
                        json.dumps(scenario, sort_keys=True, separators=(",", ":")),
                    ),
                )
    else:
        raise FixtureExportError(f"unsupported fixture bundle format {format!r}")
    return path.resolve()


def read_bundle(path: Path | str, format: str) -> dict[str, Any]:
    path = Path(path)
    try:
        if format == "json":
            result = json.loads(path.read_text(encoding="utf-8"))
        elif format == "csv":
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            if not rows:
                raise FixtureExportError("CSV bundle has no scenario rows")
            metadata_json = rows[0]["bundle_metadata_json"]
            if any(row["bundle_metadata_json"] != metadata_json for row in rows):
                raise FixtureExportError("CSV metadata differs between scenario rows")
            result = {
                **json.loads(metadata_json),
                "scenarios": [json.loads(row["scenario_json"]) for row in rows],
            }
        elif format == "sqlite":
            with sqlite3.connect(path) as connection:
                metadata = {
                    key: json.loads(value)
                    for key, value in connection.execute(
                        "SELECT key, value FROM metadata"
                    )
                }
                scenarios = [
                    json.loads(row[0])
                    for row in connection.execute(
                        "SELECT payload_json FROM scenarios ORDER BY position"
                    )
                ]
            result = {**metadata, "scenarios": scenarios}
        else:
            raise FixtureExportError(f"unsupported fixture bundle format {format!r}")
    except FixtureExportError:
        raise
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        raise FixtureExportError(
            f"cannot read {format} fixture bundle: {error}"
        ) from error
    if (
        not isinstance(result, dict)
        or result.get("version") != 1
        or not isinstance(result.get("scenarios"), list)
    ):
        raise FixtureExportError("fixture bundle has an invalid versioned envelope")
    return decode(result)


__all__ = ["FixtureExportError", "read_bundle", "write_bundle"]
