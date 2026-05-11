from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import click
import typer
from pydantic import BaseModel

from verisim.api import Verisim
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
) -> None:
    json_indent = None if compact else indent
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
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
) -> None:
    json_indent = None if compact else indent
    verisim = Verisim(
        locale=locale,
        output_language=output_language,
        script=script,
        seed=seed,
    )
    payload = _json(
        verisim.dataset(
            DatasetSpec(people=people, companies=companies, products=products)
        ),
        json_indent,
    )
    _write(payload, output)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
