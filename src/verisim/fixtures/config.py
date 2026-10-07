from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from verisim.fixtures.types import FixtureConfig

_ENVIRONMENT_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class FixtureConfigError(ValueError):
    """A fixture configuration cannot be safely loaded or validated."""


def load_config(
    path: Path | str,
    *,
    environ: Mapping[str, str] | None = None,
) -> FixtureConfig:
    """Load and validate a JSON or YAML fixture-generation configuration."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise FixtureConfigError(f"configuration file not found: {config_path}")

    environment = os.environ if environ is None else environ
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()
    try:
        if suffix == ".json":
            raw = json.loads(text)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as error:
                raise FixtureConfigError(
                    "YAML configuration requires the optional extra; install "
                    "with `uv add 'verisim[fixtures]'`"
                ) from error
            raw = yaml.safe_load(text)
        else:
            raise FixtureConfigError(
                f"unsupported config extension {suffix!r}; use .json, .yaml, or .yml"
            )
    except FixtureConfigError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise FixtureConfigError(f"invalid JSON configuration: {error}") from error
    except Exception as error:
        if error.__class__.__module__.startswith("yaml"):
            raise FixtureConfigError(f"invalid YAML configuration: {error}") from error
        raise

    if not isinstance(raw, Mapping):
        raise FixtureConfigError("configuration document must be a mapping")
    expanded = _expand_environment_variables(raw, environment)
    try:
        config = FixtureConfig.model_validate(expanded)
    except ValidationError as error:
        raise FixtureConfigError(f"invalid fixture configuration: {error}") from error

    config_dir = config_path.parent
    project_root = _resolve_path(config.project.root, config_dir)
    project_python_paths = [
        _resolve_path(python_path, project_root)
        for python_path in config.project.python_paths
    ]
    openapi_files = [
        _resolve_path(source_path, project_root)
        for source_path in config.sources.openapi.files
    ]
    output_path = _resolve_path(config.output.path, project_root)
    report_path = _resolve_path(config.output.report, project_root)
    if output_path == report_path:
        raise FixtureConfigError("fixture and report paths must be different")

    try:
        resolved = config.model_copy(
            update={
                "project": config.project.model_copy(
                    update={
                        "root": project_root,
                        "python_paths": project_python_paths,
                    }
                ),
                "sources": config.sources.model_copy(
                    update={
                        "openapi": config.sources.openapi.model_copy(
                            update={"files": openapi_files}
                        )
                    }
                ),
                "output": config.output.model_copy(
                    update={"path": output_path, "report": report_path}
                ),
            }
        )
        resolved._config_path = config_path
        return resolved
    except ValidationError as error:
        raise FixtureConfigError(
            f"invalid resolved fixture configuration: {error}"
        ) from error


def _resolve_path(path: Path, base: Path) -> Path:
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _expand_environment_variables(
    value: Any,
    environ: Mapping[str, str],
    *,
    path: str = "configuration",
) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            variable = match.group(1)
            try:
                return environ[variable]
            except KeyError as error:
                raise FixtureConfigError(
                    f"environment variable {variable!r} referenced by {path} is unset"
                ) from error

        return _ENVIRONMENT_VARIABLE.sub(replace, value)
    if isinstance(value, list):
        return [
            _expand_environment_variables(item, environ, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        return {
            key: _expand_environment_variables(item, environ, path=f"{path}.{key}")
            for key, item in value.items()
        }
    return value
