from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StrictBool,
    field_validator,
    model_validator,
)


def _require_import_reference(value: str) -> str:
    module, separator, attribute = value.partition(":")
    dotted_module = module.split(".")
    dotted_attribute = attribute.split(".")
    if (
        not separator
        or not all(part.isidentifier() for part in dotted_module)
        or not dotted_attribute
        or not all(part.isidentifier() for part in dotted_attribute)
    ):
        raise ValueError("expected an import reference in 'module:attribute' form")
    return value


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectConfig(ConfigModel):
    root: Path
    python_paths: list[Path] = Field(default_factory=list)
    revision: str = Field(min_length=1)


class OpenAPIConfig(ConfigModel):
    files: list[Path] = Field(min_length=1)


class DjangoModelsConfig(ConfigModel):
    settings_module: str = Field(min_length=1)
    models: dict[str, str] = Field(min_length=1)

    @field_validator("settings_module")
    @classmethod
    def validate_settings_module(cls, value: str) -> str:
        if not all(part.isidentifier() for part in value.split(".")):
            raise ValueError("settings_module must be a dotted Python module name")
        return value

    @field_validator("models")
    @classmethod
    def validate_model_references(cls, value: dict[str, str]) -> dict[str, str]:
        return {alias: _require_import_reference(ref) for alias, ref in value.items()}


class PythonModelsConfig(ConfigModel):
    models: dict[str, str] = Field(min_length=1)

    @field_validator("models")
    @classmethod
    def validate_model_references(cls, value: dict[str, str]) -> dict[str, str]:
        return {alias: _require_import_reference(ref) for alias, ref in value.items()}


class SourcesConfig(ConfigModel):
    openapi: OpenAPIConfig
    django: DjangoModelsConfig | None = None
    pydantic: PythonModelsConfig | None = None


class OperationConfig(ConfigModel):
    request_model: str | None = None
    fixture_models: list[str] = Field(default_factory=list)
    fixture_rows: dict[str, str] = Field(default_factory=dict)
    bindings: dict[str, str] = Field(default_factory=dict)


class CallbackConfig(ConfigModel):
    adapter: str
    options: dict[str, object] = Field(default_factory=dict)

    @field_validator("adapter")
    @classmethod
    def validate_adapter_reference(cls, value: str) -> str:
        return _require_import_reference(value)


class RunnerConfig(ConfigModel):
    runner: str
    options: dict[str, object] = Field(default_factory=dict)

    @field_validator("runner")
    @classmethod
    def validate_runner_reference(cls, value: str) -> str:
        return _require_import_reference(value)


class CandidateSeed(ConfigModel):
    operation_id: str
    values: dict[str, object]
    expectations: dict[str, object] = Field(default_factory=dict)


class GenerationConfig(ConfigModel):
    seed: int | None = None
    clock: datetime
    candidate_limit: int = Field(ge=1)
    candidates: list[CandidateSeed] = Field(default_factory=list)


class MinimizationConfig(ConfigModel):
    unit: Literal["scenario"]
    method: Literal["exact_set_cover"]
    require_full_coverage: StrictBool
    timeout_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def require_complete_coverage(self) -> MinimizationConfig:
        if self.require_full_coverage is not True:
            raise ValueError("require_full_coverage must be true")
        return self


class OutputConfig(ConfigModel):
    format: Literal["json", "csv", "sqlite"]
    path: Path
    report: Path


class FixtureConfig(ConfigModel):
    _config_path: Path | None = PrivateAttr(default=None)
    version: Literal[1]
    project: ProjectConfig
    sources: SourcesConfig
    operations: dict[str, OperationConfig] = Field(min_length=1)
    branches: CallbackConfig
    execution: RunnerConfig
    generation: GenerationConfig
    minimization: MinimizationConfig
    output: OutputConfig

    @model_validator(mode="after")
    def validate_references(self) -> FixtureConfig:
        missing_seed_operations = {
            seed.operation_id
            for seed in self.generation.candidates
            if seed.operation_id not in self.operations
        }
        if missing_seed_operations:
            raise ValueError(
                "generation candidate seeds reference unknown operations: "
                f"{sorted(missing_seed_operations)}"
            )

        if self.sources.django is None and any(
            operation.fixture_models or operation.fixture_rows
            for operation in self.operations.values()
        ):
            raise ValueError("fixture models require a Django model source")

        django_aliases = (
            set(self.sources.django.models) if self.sources.django else set()
        )
        pydantic_aliases = (
            set(self.sources.pydantic.models) if self.sources.pydantic else set()
        )
        overlap = django_aliases & pydantic_aliases
        if overlap:
            raise ValueError(
                f"model aliases must be unique across sources: {sorted(overlap)}"
            )

        for operation_id, operation in self.operations.items():
            if operation.request_model is not None and (
                self.sources.pydantic is None
                or operation.request_model not in self.sources.pydantic.models
            ):
                raise ValueError(
                    f"operation {operation_id!r} references an unknown Pydantic "
                    f"request model {operation.request_model!r}"
                )

            unknown_models = set(operation.fixture_models) - django_aliases
            if unknown_models:
                raise ValueError(
                    f"operation {operation_id!r} references unknown Django model "
                    f"aliases: {sorted(unknown_models)}"
                )
            if len(set(operation.fixture_models)) != len(operation.fixture_models):
                raise ValueError(
                    f"operation {operation_id!r} repeats a fixture model alias"
                )

            repeated_rows = set(operation.fixture_rows) & set(operation.fixture_models)
            if repeated_rows:
                raise ValueError(
                    f"operation {operation_id!r} fixture row refs shadow model "
                    f"aliases: {sorted(repeated_rows)}"
                )

            for row_ref, model_alias in operation.fixture_rows.items():
                if not row_ref or "." in row_ref:
                    raise ValueError(
                        f"operation {operation_id!r} has an invalid fixture row "
                        f"reference {row_ref!r}"
                    )
                if model_alias not in operation.fixture_models:
                    raise ValueError(
                        f"operation {operation_id!r} row ref {row_ref!r} must map "
                        "to one of its fixture_models"
                    )

        if self.output.path == self.output.report:
            raise ValueError("fixture and report paths must be different")
        return self
