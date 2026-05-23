from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal

import click
import typer
from pydantic import BaseModel

from verisim.api import Verisim
from verisim.exporters import export_dataset, export_records
from verisim.models import (
    Address,
    CompanyRecord,
    Contact,
    DatasetSpec,
    Job,
    PersonRecord,
    ProductRecord,
    Socials,
    Website,
)

CliExportFormat = Literal[
    "json", "jsonl", "csv", "sql", "sqlite", "parquet", "feather", "arrow", "avro"
]
CliLayout = Literal["relational", "wide", "both"]
CliSqlMode = Literal["copy", "insert"]


class VerisimTyperGroup(typer.core.TyperGroup):
    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as error:
            if args and not args[0].startswith("-"):
                supported = ", ".join(sorted(set(TARGETS) | {"dataset"}))
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

TARGETS: dict[str, type[BaseModel]] = {
    "address": Address,
    "company": CompanyRecord,
    "company-record": CompanyRecord,
    "contact": Contact,
    "job": Job,
    "person": PersonRecord,
    "person-record": PersonRecord,
    "product": ProductRecord,
    "product-record": ProductRecord,
    "socials": Socials,
    "website": Website,
}


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


def _json(model: BaseModel, indent: int | None) -> str:
    return model.model_dump_json(indent=indent)


def _write(text: str, output: Path | None) -> None:
    if output is None:
        typer.echo(text)
        return
    output.write_text(f"{text}\n")


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
        export_records(
            verisim.iter_records(model, repeat),
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
        _json(record, json_indent) for record in verisim.records(model, repeat)
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
) -> None:
    json_indent = None if compact else indent
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    spec = DatasetSpec(people=people, companies=companies, products=products)
    if export_format == "json":
        payload = _json(verisim.dataset(spec), json_indent)
        _write(payload, output)
        return
    if output is None:
        raise typer.BadParameter("--output is required when --format is not json")
    export_dataset(
        verisim.iter_dataset(spec),
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


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
