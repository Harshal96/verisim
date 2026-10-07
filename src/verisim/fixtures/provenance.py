"""Snapshots and identities needed to audit a generated bundle."""

from __future__ import annotations

import hashlib
import inspect
import json
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from verisim.fixtures.codec import encode


def snapshot(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, SimpleNamespace):
        return {key: snapshot(item) for key, item in vars(value).items()}
    if isinstance(value, dict):
        return {key: snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [snapshot(item) for item in value]
    return encode(value)


def fingerprint(value: Any) -> str:
    payload = json.dumps(
        snapshot(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def callback_identity(callback: Any, reference: str, options: dict) -> dict[str, Any]:
    identity = {
        "reference": reference,
        "module": callback.__module__,
        "qualname": getattr(callback, "__qualname__", type(callback).__qualname__),
        "options": snapshot(options),
        "source_path": None,
        "source_sha256": None,
        "distribution_version": None,
    }
    try:
        path = Path(inspect.getfile(callback)).resolve()
        if path.is_file():
            identity["source_path"] = str(path)
            identity["source_sha256"] = (
                "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            )
    except (OSError, TypeError):
        pass
    distributions = metadata.packages_distributions().get(
        callback.__module__.split(".")[0], []
    )
    if distributions:
        identity["distribution_version"] = metadata.version(distributions[0])
    return identity


def build_provenance(
    config: Any, sources: Any, catalog: Any, provider: Any, runner: Any
) -> dict:
    try:
        version = metadata.version("verisim")
    except metadata.PackageNotFoundError:
        version = "uninstalled"

    root = Path(__file__).resolve().parents[1]
    source_digests = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".json", ".csv", ".yaml", ".yml"}
    }
    catalog_snapshot = {
        "version": 1,
        "source_revision": catalog.source_revision,
        "scope": {"complete": True, "operations": list(catalog.operations)},
        "targets": [
            {
                "id": t.id,
                "operation_id": t.operation_id,
                "arc": t.arc,
                "constraints": list(t.constraints),
            }
            for t in catalog.targets
        ],
    }
    config_snapshot = snapshot(config)
    files = set(sources.files)
    for target in catalog.targets:
        if target.arc:
            path = (config.project.root / target.arc["file"]).resolve()
            if path.is_file():
                files.add(path)
    config_path = getattr(config, "_config_path", None)
    if config_path:
        files.add(config_path)
    if config.branches.adapter == "verisim.fixtures.adapters.file:load_branches":
        files.add((config.project.root / config.branches.options["path"]).resolve())
    return {
        "config": config_snapshot,
        "config_fingerprint": fingerprint(config_snapshot),
        "catalog": catalog_snapshot,
        "catalog_fingerprint": fingerprint(catalog_snapshot),
        "source_files": {
            str(p): "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)
        },
        "branch_adapter": callback_identity(
            provider, config.branches.adapter, config.branches.options
        ),
        "runner": callback_identity(
            runner, config.execution.runner, config.execution.options
        ),
        "library": {
            "version": version,
            "source_fingerprint": fingerprint(source_digests),
        },
        "data_pack_fingerprint": fingerprint(
            {k: v for k, v in source_digests.items() if not k.endswith(".py")}
        ),
        "required_replay_adapters": [config.execution.runner],
        "effective_clock": snapshot(config.generation.clock),
    }
