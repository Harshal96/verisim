from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal

import click
import typer
from pydantic import BaseModel

from verisim.activity import (
    ActivityStreamSpec,
    JsonlActivitySink,
    KafkaActivitySink,
    emit_activity_stream,
)
from verisim.ai import (
    ChatDatasetSpec,
    ClassificationDatasetSpec,
    InstructionDatasetSpec,
    NerDatasetSpec,
    chat_dataset,
    classification_dataset,
    instruction_dataset,
    iter_chat_transcripts,
    iter_classification_examples,
    iter_instruction_pairs,
    iter_ner_sequences,
    ner_dataset,
)
from verisim.api import Verisim
from verisim.exporters import (
    export_dataset,
    export_records,
    write_json_schema,
    write_openapi_components,
)
from verisim.models import (
    Address,
    CompanyRecord,
    Contact,
    DatasetSpec,
    EventRecord,
    Job,
    MedicalRecord,
    OrderRecord,
    PersonRecord,
    ProductRecord,
    ReviewRecord,
    Socials,
    SupportTicketRecord,
    TransactionRecord,
    Website,
)

CliExportFormat = Literal[
    "json", "jsonl", "csv", "sql", "sqlite", "parquet", "feather", "arrow", "avro"
]
CliLayout = Literal["relational", "wide", "both"]
CliSqlMode = Literal["copy", "insert"]
CliActivitySink = Literal["jsonl", "kafka"]
CliAIFormat = Literal["json", "jsonl"]
CliSchemaDialect = Literal["json-schema-2020-12", "openapi-3.1"]
CliGenerationMode = Literal[
    "strict", "repair", "explain", "edge_cases", "schema_violations"
]


class VerisimTyperGroup(typer.core.TyperGroup):
    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as error:
            if args and not args[0].startswith("-"):
                supported = ", ".join(
                    sorted(set(TARGETS) | {"activity-stream", "ai", "dataset"})
                )
                raise click.UsageError(
                    f"unsupported target. Choose one of: {supported}",
                    ctx=ctx,
                ) from error
            raise  # pragma: no cover


app = typer.Typer(
    cls=VerisimTyperGroup,
    add_completion=False,
    no_args_is_help=True,
)
ai_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(ai_app, name="ai")

TARGETS: dict[str, type[BaseModel]] = {
    "address": Address,
    "company": CompanyRecord,
    "company-record": CompanyRecord,
    "contact": Contact,
    "job": Job,
    "event": EventRecord,
    "event-record": EventRecord,
    "medical": MedicalRecord,
    "medical-record": MedicalRecord,
    "order": OrderRecord,
    "order-record": OrderRecord,
    "person": PersonRecord,
    "person-record": PersonRecord,
    "product": ProductRecord,
    "product-record": ProductRecord,
    "review": ReviewRecord,
    "review-record": ReviewRecord,
    "socials": Socials,
    "support-ticket": SupportTicketRecord,
    "support-ticket-record": SupportTicketRecord,
    "transaction": TransactionRecord,
    "transaction-record": TransactionRecord,
    "website": Website,
}


@app.command("schema")
def schema_command(
    target: Annotated[str, typer.Argument(help="Built-in Verisim target name.")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    dialect: Annotated[CliSchemaDialect, typer.Option("--dialect")] = (
        "json-schema-2020-12"
    ),
) -> None:
    model = TARGETS.get(target)
    if model is None:
        supported = ", ".join(sorted(TARGETS))
        raise typer.BadParameter(f"unsupported target. Choose one of: {supported}")
    if dialect == "openapi-3.1":
        write_openapi_components([model], output)
        return
    write_json_schema(model, output, dialect=dialect)


def _package_version() -> str:
    try:
        return version("verisim")
    except PackageNotFoundError:
        return "0.0.0"


def _version_callback(show_version: bool) -> None:
    if show_version:
        typer.echo(f"verisim {_package_version()}")
        raise typer.Exit()


@app.callback()
def callback(
    version_option: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the installed Verisim version.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    _ = version_option


@app.command("fixtures")
def fixtures_command(
    config_path: Annotated[
        Path, typer.Option("--config", help="Fixture generation YAML or JSON config.")
    ],
    output_format: Annotated[
        Literal["json", "csv", "sqlite"] | None,
        typer.Option("--format", help="Override the configured bundle format."),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", help="Override the fixture bundle path.")
    ] = None,
) -> None:
    """Generate the fewest replayable scenarios covering the branch catalog."""
    from verisim.fixtures.config import load_config
    from verisim.fixtures.pipeline import generate_fixtures

    report_path: str | None = None
    try:
        fixture_config = load_config(config_path)
        report_path = str(fixture_config.output.report)
        updates: dict[str, object] = {}
        if output_format is not None:
            updates["format"] = output_format
        if output is not None:
            updates["path"] = (
                output if output.is_absolute() else fixture_config.project.root / output
            )
        if updates:
            fixture_config = fixture_config.model_copy(
                update={"output": fixture_config.output.model_copy(update=updates)}
            )
        result = generate_fixtures(fixture_config)
        typer.echo(json.dumps(result.to_dict(), sort_keys=True))
        exit_codes = {
            "complete": 0,
            "checks_failed": 4,
            "coverage_incomplete": 3,
            "optimization_incomplete": 3,
            "replay_failed": 3,
            "publication_failed": 5,
        }
        if result.status not in exit_codes:
            raise typer.Exit(2)
        if exit_codes[result.status]:
            raise typer.Exit(exit_codes[result.status])
    except typer.Exit:
        raise
    except Exception as error:
        typer.echo(f"fixture generation failed: {error}", err=True)
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "run_id": None,
                    "fixture_path": None,
                    "report_path": report_path,
                    "fixture_sha256": None,
                    "scenario_count": 0,
                    "coverage_complete": False,
                    "optimal_within_pool": False,
                    "replay_verified": False,
                    "checks_passed": False,
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(2) from error


def _json(model: BaseModel, indent: int | None) -> str:
    return model.model_dump_json(indent=indent)


def _write(text: str, output: Path | None) -> None:
    if output is None:
        typer.echo(text)
        return
    output.write_text(f"{text}\n")


def _write_lines(lines: Iterable[str], output: Path | None) -> None:
    text = "\n".join(lines)
    if output is None:
        if text:
            typer.echo(text)
        return
    output.write_text(f"{text}\n" if text else "")


def _generate_records(
    model: type[BaseModel],
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    repeat: Annotated[int, typer.Option("--repeat", "-r", min=1)] = 1,
    separator: Annotated[str, typer.Option("--separator", "-s")] = "\n",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
    compact: Annotated[bool, typer.Option("--compact")] = False,
    export_format: Annotated[CliExportFormat, typer.Option("--format")] = "json",
    batch_size: Annotated[int, typer.Option("--batch-size", min=1)] = 10_000,
    mode: Annotated[CliGenerationMode, typer.Option("--mode")] = "strict",
    edge_case: Annotated[str | None, typer.Option("--edge-case")] = None,
    violation: Annotated[str | None, typer.Option("--violation")] = None,
    duplicate_percent: Annotated[
        int, typer.Option("--duplicate-percent", min=0, max=100)
    ] = 0,
) -> None:
    json_indent = None if compact else indent
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    if export_format != "json":
        if output is None:
            raise typer.BadParameter("--output is required when --format is not json")
        records = (
            verisim.records(
                model,
                repeat,
                mode=mode,
                edge_case=edge_case,
                violation=violation,
                duplicate_percent=duplicate_percent,
            )
            if duplicate_percent
            else verisim.iter_records(
                model,
                repeat,
                mode=mode,
                edge_case=edge_case,
                violation=violation,
            )
        )
        export_records(
            records,
            model,
            export_format,
            output,
            batch_size=batch_size,
            metadata={
                "locale": locale,
                "output_language": output_language,
                "script": script,
                "seed": seed,
            },
        )
        return
    payload = separator.join(
        _json(record, json_indent)
        for record in verisim.records(
            model,
            repeat,
            mode=mode,
            edge_case=edge_case,
            violation=violation,
            duplicate_percent=duplicate_percent,
        )
    )
    _write(payload, output)


def _record_command(model: type[BaseModel]):
    def command(
        locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
        output_language: Annotated[str, typer.Option("--output-language")] = "en",
        script: Annotated[str, typer.Option("--script")] = "latin",
        seed: Annotated[int | None, typer.Option("--seed")] = None,
        repeat: Annotated[int, typer.Option("--repeat", "-r", min=1)] = 1,
        separator: Annotated[str, typer.Option("--separator", "-s")] = "\n",
        output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
        indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
        compact: Annotated[bool, typer.Option("--compact")] = False,
        export_format: Annotated[CliExportFormat, typer.Option("--format")] = "json",
        batch_size: Annotated[int, typer.Option("--batch-size", min=1)] = 10_000,
        mode: Annotated[CliGenerationMode, typer.Option("--mode")] = "strict",
        edge_case: Annotated[str | None, typer.Option("--edge-case")] = None,
        violation: Annotated[str | None, typer.Option("--violation")] = None,
        duplicate_percent: Annotated[
            int, typer.Option("--duplicate-percent", min=0, max=100)
        ] = 0,
    ) -> None:
        _generate_records(
            model=model,
            locale=locale,
            output_language=output_language,
            script=script,
            seed=seed,
            repeat=repeat,
            separator=separator,
            output=output,
            indent=indent,
            compact=compact,
            export_format=export_format,
            batch_size=batch_size,
            mode=mode,
            edge_case=edge_case,
            violation=violation,
            duplicate_percent=duplicate_percent,
        )

    return command


for target_name, target_model in TARGETS.items():
    generated_command = _record_command(target_model)
    generated_command.__name__ = target_name.replace("-", "_")
    app.command(target_name)(generated_command)


@app.command()
def dataset(
    people: Annotated[int, typer.Option("--people", min=0)] = 10,
    companies: Annotated[int, typer.Option("--companies", min=0)] = 3,
    products: Annotated[int, typer.Option("--products", min=0)] = 0,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
    compact: Annotated[bool, typer.Option("--compact")] = False,
    export_format: Annotated[CliExportFormat, typer.Option("--format")] = "json",
    layout: Annotated[CliLayout, typer.Option("--layout")] = "relational",
    sql_mode: Annotated[CliSqlMode, typer.Option("--sql-mode")] = "copy",
    batch_size: Annotated[int, typer.Option("--batch-size", min=1)] = 10_000,
    mode: Annotated[CliGenerationMode, typer.Option("--mode")] = "strict",
    edge_case: Annotated[str | None, typer.Option("--edge-case")] = None,
    violation: Annotated[str | None, typer.Option("--violation")] = None,
    people_duplicate_percent: Annotated[
        int, typer.Option("--people-duplicate-percent", min=0, max=100)
    ] = 0,
    companies_duplicate_percent: Annotated[
        int, typer.Option("--companies-duplicate-percent", min=0, max=100)
    ] = 0,
    products_duplicate_percent: Annotated[
        int, typer.Option("--products-duplicate-percent", min=0, max=100)
    ] = 0,
) -> None:
    json_indent = None if compact else indent
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    spec = DatasetSpec(
        people=people,
        companies=companies,
        products=products,
        people_duplicate_percent=people_duplicate_percent,
        companies_duplicate_percent=companies_duplicate_percent,
        products_duplicate_percent=products_duplicate_percent,
    )
    if export_format == "json":
        payload = _json(
            verisim.dataset(
                spec,
                mode=mode,
                edge_case=edge_case,
                violation=violation,
            ),
            json_indent,
        )
        _write(payload, output)
        return
    if output is None:
        raise typer.BadParameter("--output is required when --format is not json")
    export_dataset(
        verisim.iter_dataset(
            spec,
            mode=mode,
            edge_case=edge_case,
            violation=violation,
        ),
        export_format,
        output,
        layout=layout,
        sql_mode=sql_mode,
        batch_size=batch_size,
        metadata={
            "locale": locale,
            "output_language": output_language,
            "script": script,
            "seed": seed,
        },
    )


@ai_app.command("instruction-pairs")
def ai_instruction_pairs(
    count: Annotated[int, typer.Option("--count", min=0)] = 10,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
    compact: Annotated[bool, typer.Option("--compact")] = False,
    export_format: Annotated[CliAIFormat, typer.Option("--format")] = "json",
) -> None:
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    spec = InstructionDatasetSpec(count=count)
    if export_format == "json":
        json_indent = None if compact else indent
        _write(_json(instruction_dataset(verisim, spec), json_indent), output)
        return
    _write_lines(
        (record.model_dump_json() for record in iter_instruction_pairs(verisim, spec)),
        output,
    )


@ai_app.command("classification")
def ai_classification(
    count: Annotated[int, typer.Option("--count", min=0)] = 10,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
    compact: Annotated[bool, typer.Option("--compact")] = False,
    export_format: Annotated[CliAIFormat, typer.Option("--format")] = "json",
    labels: Annotated[
        list[str] | None,
        typer.Option("--label", help="Class distribution entry as label=weight."),
    ] = None,
    label_noise: Annotated[
        float, typer.Option("--label-noise", min=0.0, max=1.0)
    ] = 0.0,
) -> None:
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    spec = ClassificationDatasetSpec(
        count=count,
        labels=_parse_label_weights(labels),
        label_noise=label_noise,
    )
    if export_format == "json":
        json_indent = None if compact else indent
        _write(_json(classification_dataset(verisim, spec), json_indent), output)
        return
    _write_lines(
        (
            record.model_dump_json()
            for record in iter_classification_examples(verisim, spec)
        ),
        output,
    )


@ai_app.command("ner")
def ai_ner(
    count: Annotated[int, typer.Option("--count", min=0)] = 10,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
    compact: Annotated[bool, typer.Option("--compact")] = False,
    export_format: Annotated[CliAIFormat, typer.Option("--format")] = "json",
) -> None:
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    spec = NerDatasetSpec(count=count)
    if export_format == "json":
        json_indent = None if compact else indent
        _write(_json(ner_dataset(verisim, spec), json_indent), output)
        return
    _write_lines(
        (record.model_dump_json() for record in iter_ner_sequences(verisim, spec)),
        output,
    )


@ai_app.command("chat")
def ai_chat(
    count: Annotated[int, typer.Option("--count", min=0)] = 10,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    indent: Annotated[int | None, typer.Option("--indent", min=0)] = None,
    compact: Annotated[bool, typer.Option("--compact")] = False,
    export_format: Annotated[CliAIFormat, typer.Option("--format")] = "json",
    min_turns: Annotated[int, typer.Option("--min-turns", min=1)] = 2,
    max_turns: Annotated[int, typer.Option("--max-turns", min=1)] = 4,
) -> None:
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    spec = ChatDatasetSpec(count=count, min_turns=min_turns, max_turns=max_turns)
    if export_format == "json":
        json_indent = None if compact else indent
        _write(_json(chat_dataset(verisim, spec), json_indent), output)
        return
    _write_lines(
        (record.model_dump_json() for record in iter_chat_transcripts(verisim, spec)),
        output,
    )


def _parse_label_weights(labels: list[str] | None) -> dict[str, float]:
    if not labels:
        return ClassificationDatasetSpec().labels
    parsed: dict[str, float] = {}
    for label in labels:
        if "=" not in label:
            raise typer.BadParameter("--label must use label=weight")
        name, weight_text = label.split("=", maxsplit=1)
        name = name.strip()
        if not name:
            raise typer.BadParameter("--label names must not be blank")
        try:
            weight = float(weight_text)
        except ValueError as error:
            raise typer.BadParameter("--label weights must be numeric") from error
        if weight <= 0:
            raise typer.BadParameter("--label weights must be positive")
        parsed[name] = weight
    return parsed


def _parse_datetime_option(value: str | None, option_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise typer.BadParameter(
            f"{option_name} must be an ISO-8601 datetime"
        ) from error


@app.command("activity-stream")
def activity_stream(
    people: Annotated[int, typer.Option("--people", min=1)] = 1,
    events_per_person: Annotated[int, typer.Option("--events-per-person", min=1)] = 100,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en_US",
    output_language: Annotated[str, typer.Option("--output-language")] = "en",
    script: Annotated[str, typer.Option("--script")] = "latin",
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    sink: Annotated[CliActivitySink, typer.Option("--sink")] = "jsonl",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    throughput: Annotated[float | None, typer.Option("--throughput", min=0.0)] = None,
    start_at: Annotated[str | None, typer.Option("--start-at")] = None,
    end_at: Annotated[str | None, typer.Option("--end-at")] = None,
    bootstrap_servers: Annotated[
        str | None, typer.Option("--bootstrap-servers")
    ] = None,
    topic: Annotated[str | None, typer.Option("--topic")] = None,
) -> None:
    if throughput is not None and throughput <= 0:
        raise typer.BadParameter("--throughput must be greater than 0")
    spec = ActivityStreamSpec(
        people=people,
        events_per_person=events_per_person,
        start_at=_parse_datetime_option(start_at, "--start-at"),
        end_at=_parse_datetime_option(end_at, "--end-at"),
    )
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    events = verisim.iter_activity_stream(spec)
    if sink == "jsonl":
        activity_sink = (
            JsonlActivitySink.from_path(output)
            if output is not None
            else JsonlActivitySink(sys.stdout)
        )
    else:
        missing = []
        if bootstrap_servers is None:
            missing.append("--bootstrap-servers is required")
        if topic is None:
            missing.append("--topic is required")
        if missing:
            raise typer.BadParameter("; ".join(missing))
        activity_sink = KafkaActivitySink(
            topic=topic,
            bootstrap_servers=bootstrap_servers,
        )
    emit_activity_stream(events, activity_sink, throughput_rps=throughput)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
