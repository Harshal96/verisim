from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from verisim.models import Dataset, DatasetEvent

from .projectors import DatasetProjector, Row, events_from_dataset, flatten_record
from .schema import (
    ExportFormat,
    ExportLayout,
    SqlMode,
    TableSchema,
    schema_by_name,
)

EXPORT_INSTALL_HINT = "Install optional export dependencies with `verisim[export]`."


def export_dataset(
    source: Dataset | Iterable[DatasetEvent],
    format: ExportFormat,
    output: Path | str,
    *,
    layout: ExportLayout = "relational",
    sql_mode: SqlMode = "copy",
    batch_size: int = 10_000,
    metadata: Mapping[str, object] | None = None,
) -> None:
    path = Path(output)
    if format == "json":
        if not isinstance(source, Dataset):
            raise ValueError("json dataset export requires a materialized Dataset")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{source.model_dump_json(indent=2)}\n", encoding="utf-8")
        return
    if format == "jsonl":
        _write_dataset_jsonl(_dataset_events(source), path)
        return
    if format in {"parquet", "feather", "arrow"}:
        _write_dataset_arrow(
            _dataset_events(source), format, path, layout, batch_size, metadata
        )
        return
    if format == "avro":
        _write_dataset_avro(_dataset_events(source), path, layout, batch_size, metadata)
        return
    if format == "csv":
        writer = CsvDatasetWriter(path, layout)
    elif format == "sqlite":
        writer = SqliteDatasetWriter(path, layout)
    elif format == "sql":
        writer = SqlDatasetWriter(path, layout, sql_mode, batch_size)
    else:
        raise ValueError(f"unsupported export format {format!r}")
    _write_dataset_rows(_dataset_events(source), writer, layout, metadata)


def export_records(
    records: Iterable[BaseModel],
    model: type[BaseModel],
    format: ExportFormat,
    output: Path | str,
    *,
    batch_size: int = 10_000,
    metadata: Mapping[str, object] | None = None,
) -> None:
    del metadata
    path = Path(output)
    if format == "json":
        rows = list(records)
        if len(rows) != 1:
            raise ValueError("json record export requires exactly one record")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rows[0].model_dump_json(indent=2)}\n", encoding="utf-8")
        return
    if format == "jsonl":
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(f"{record.model_dump_json()}\n")
        return

    table_name = _record_table_name(model)
    rows = (flatten_record(record) for record in records)
    if format == "csv":
        _write_record_csv(rows, path)
        return
    if format == "sql":
        _write_record_sql(rows, table_name, path)
        return
    if format in {"parquet", "feather", "arrow"}:
        _write_record_arrow(rows, format, table_name, path, batch_size)
        return
    if format == "avro":
        _write_record_avro(rows, table_name, path, batch_size)
        return
    raise ValueError(f"unsupported export format {format!r}")


class CsvDatasetWriter:
    def __init__(self, directory: Path, layout: ExportLayout) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.schemas = schema_by_name(layout)
        self.streams: dict[str, Any] = {}
        self.writers: dict[str, csv.DictWriter] = {}
        for schema in self.schemas.values():
            self._open(schema)

    def write(self, table: str, row: Row) -> None:
        writer = self.writers[table]
        writer.writerow(
            {column: _csv_value(row.get(column)) for column in writer.fieldnames}
        )

    def close(self) -> None:
        for stream in self.streams.values():
            stream.close()

    def _open(self, schema: TableSchema) -> None:
        stream = (self.directory / f"{schema.name}.csv").open(
            "w", newline="", encoding="utf-8"
        )
        writer = csv.DictWriter(stream, fieldnames=list(schema.column_names))
        writer.writeheader()
        self.streams[schema.name] = stream
        self.writers[schema.name] = writer


class SqliteDatasetWriter:
    def __init__(self, path: Path, layout: ExportLayout) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        self.schemas = schema_by_name(layout)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(_schema_sql(tuple(self.schemas.values())))

    def write(self, table: str, row: Row) -> None:
        schema = self.schemas[table]
        columns = list(schema.column_names)
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)
        values = [row.get(column) for column in columns]
        self.connection.execute(
            f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})", values
        )

    def close(self) -> None:
        violations = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(f"foreign key check failed: {violations}")
        self.connection.commit()
        self.connection.close()


class SqlDatasetWriter:
    def __init__(
        self, path: Path, layout: ExportLayout, sql_mode: SqlMode, batch_size: int
    ) -> None:
        self.path = path
        self.schemas = schema_by_name(layout)
        self.sql_mode = sql_mode
        self.batch_size = batch_size
        self.tempdir = tempfile.TemporaryDirectory()
        self.row_counts = {name: 0 for name in self.schemas}

    def write(self, table: str, row: Row) -> None:
        schema = self.schemas[table]
        path = Path(self.tempdir.name) / f"{table}.rows"
        with path.open("a", encoding="utf-8") as stream:
            if self.sql_mode == "copy":
                stream.write(_copy_line(schema, row))
            else:
                stream.write(f"{_insert_tuple(schema, row)}\n")
        self.row_counts[table] += 1

    def close(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schemas = tuple(self.schemas.values())
        with self.path.open("w", encoding="utf-8") as stream:
            stream.write("-- Verisim synthetic data export\n")
            stream.write("BEGIN;\n\n")
            stream.write(_schema_sql(schemas))
            if self.sql_mode == "copy":
                self._write_copy_blocks(stream, schemas)
            else:
                self._write_insert_blocks(stream, schemas)
            stream.write("COMMIT;\n")
        self.tempdir.cleanup()

    def _write_copy_blocks(self, stream, schemas: tuple[TableSchema, ...]) -> None:
        for schema in schemas:
            row_file = Path(self.tempdir.name) / f"{schema.name}.rows"
            if not row_file.exists():
                continue
            columns = ", ".join(schema.column_names)
            stream.write(f"COPY {schema.name} ({columns}) FROM stdin;\n")
            stream.write(row_file.read_text(encoding="utf-8"))
            stream.write("\\.\n\n")

    def _write_insert_blocks(self, stream, schemas: tuple[TableSchema, ...]) -> None:
        for schema in schemas:
            row_file = Path(self.tempdir.name) / f"{schema.name}.rows"
            if not row_file.exists():
                continue
            columns = ", ".join(schema.column_names)
            rows = row_file.read_text(encoding="utf-8").splitlines()
            for start in range(0, len(rows), self.batch_size):
                chunk = rows[start : start + self.batch_size]
                stream.write(f"INSERT INTO {schema.name} ({columns}) VALUES\n")
                stream.write(",\n".join(chunk))
                stream.write(";\n\n")


def _write_dataset_rows(
    events: Iterable[DatasetEvent],
    writer,
    layout: ExportLayout,
    metadata: Mapping[str, object] | None,
) -> None:
    projector = DatasetProjector(layout=layout, metadata=metadata)
    try:
        for event in events:
            for table, row in projector.project(event):
                writer.write(table, row)
        for table, row in projector.metadata_rows():
            writer.write(table, row)
    finally:
        writer.close()


def _write_dataset_jsonl(events: Iterable[DatasetEvent], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for event in events:
            record = event.record
            stream.write(
                json.dumps(
                    {"kind": event.kind, "record": record.model_dump(mode="json")},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            stream.write("\n")


def _dataset_events(source: Dataset | Iterable[DatasetEvent]) -> Iterable[DatasetEvent]:
    if isinstance(source, Dataset):
        return events_from_dataset(source)
    return source


def _write_dataset_arrow(
    events: Iterable[DatasetEvent],
    format: str,
    path: Path,
    layout: ExportLayout,
    batch_size: int,
    metadata: Mapping[str, object] | None,
) -> None:
    pa, pq = _require_pyarrow()
    writer = ArrowDatasetWriter(pa, pq, path, layout, format, batch_size)
    _write_dataset_rows(events, writer, layout, metadata)


def _write_dataset_avro(
    events: Iterable[DatasetEvent],
    path: Path,
    layout: ExportLayout,
    batch_size: int,
    metadata: Mapping[str, object] | None,
) -> None:
    fastavro = _require_fastavro()
    writer = AvroDatasetWriter(fastavro, path, layout, batch_size)
    _write_dataset_rows(events, writer, layout, metadata)


class ArrowDatasetWriter:
    def __init__(
        self,
        pa,
        pq,
        directory: Path,
        layout: ExportLayout,
        format: str,
        batch_size: int,
    ) -> None:
        self.pa = pa
        self.pq = pq
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.schemas = schema_by_name(layout)
        self.format = format
        self.batch_size = batch_size
        self.buffers = {name: [] for name in self.schemas}
        self.writers: dict[str, Any] = {}

    def write(self, table: str, row: Row) -> None:
        self.buffers[table].append(row)
        if len(self.buffers[table]) >= self.batch_size:
            self._flush(table)

    def close(self) -> None:
        for table in self.schemas:
            self._flush(table, create_empty=True)
        for writer in self.writers.values():
            writer.close()

    def _flush(self, table: str, create_empty: bool = False) -> None:
        rows = self.buffers[table]
        if not rows and table in self.writers:
            return
        if not rows and not create_empty:
            return
        schema = self._arrow_schema(self.schemas[table])
        arrow_table = self.pa.Table.from_pylist(rows, schema=schema)
        writer = self.writers.get(table)
        if writer is None:
            writer = self._open_writer(table, schema)
            self.writers[table] = writer
        if len(rows) or create_empty:
            if self.format == "parquet":
                writer.write_table(arrow_table)
            else:
                for batch in arrow_table.to_batches():
                    writer.write_batch(batch)
        self.buffers[table] = []

    def _open_writer(self, table: str, schema):
        suffix = {"parquet": "parquet", "feather": "feather", "arrow": "arrow"}[
            self.format
        ]
        path = self.directory / f"{table}.{suffix}"
        if self.format == "parquet":
            return self.pq.ParquetWriter(path, schema)
        if self.format == "arrow":
            return self.pa.ipc.new_stream(path, schema)
        return self.pa.ipc.new_file(path, schema)

    def _arrow_schema(self, schema: TableSchema):
        return self.pa.schema(
            [
                self.pa.field(
                    column.name,
                    {
                        "TEXT": self.pa.string(),
                        "INTEGER": self.pa.int64(),
                        "REAL": self.pa.float64(),
                    }[column.sql_type],
                    nullable=True,
                )
                for column in schema.columns
            ]
        )


class AvroDatasetWriter:
    def __init__(
        self, fastavro, directory: Path, layout: ExportLayout, batch_size: int
    ) -> None:
        self.fastavro = fastavro
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.schemas = schema_by_name(layout)
        self.batch_size = batch_size
        self.buffers = {name: [] for name in self.schemas}
        self.written = {name: False for name in self.schemas}

    def write(self, table: str, row: Row) -> None:
        self.buffers[table].append(row)
        if len(self.buffers[table]) >= self.batch_size:
            self._flush(table)

    def close(self) -> None:
        for table in self.schemas:
            self._flush(table, create_empty=True)

    def _flush(self, table: str, create_empty: bool = False) -> None:
        rows = self.buffers[table]
        if not rows and self.written[table]:
            return
        if not rows and not create_empty:
            return
        path = self.directory / f"{table}.avro"
        mode = "a+b" if self.written[table] else "wb"
        schema = None if self.written[table] else _avro_schema(self.schemas[table])
        with path.open(mode) as stream:
            self.fastavro.writer(stream, schema, rows)
        self.written[table] = True
        self.buffers[table] = []


def _write_record_csv(rows: Iterable[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    iterator = iter(rows)
    first = next(iterator, None)
    if first is None:
        path.write_text("", encoding="utf-8")
        return
    headers = list(first)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerow({column: _csv_value(first.get(column)) for column in headers})
        for row in iterator:
            writer.writerow({column: _csv_value(row.get(column)) for column in headers})


def _write_record_sql(rows: Iterable[Row], table_name: str, path: Path) -> None:
    iterator = iter(rows)
    first = next(iterator, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    if first is None:
        path.write_text("", encoding="utf-8")
        return
    schema = TableSchema(
        table_name,
        tuple(_column_from_value(name, value) for name, value in first.items()),
    )
    with path.open("w", encoding="utf-8") as stream:
        stream.write(_schema_sql((schema,)))
        values = [_insert_tuple(schema, first)]
        for row in iterator:
            values.append(_insert_tuple(schema, row))
        stream.write(
            f"INSERT INTO {table_name} ({', '.join(schema.column_names)}) VALUES\n"
        )
        stream.write(",\n".join(values))
        stream.write(";\n")


def _write_record_arrow(
    rows: Iterable[Row], format: str, table_name: str, path: Path, batch_size: int
) -> None:
    pa, pq = _require_pyarrow()
    del table_name, batch_size
    data = list(rows)
    table = pa.Table.from_pylist(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "parquet":
        pq.write_table(table, path)
    elif format == "arrow":
        with pa.ipc.new_stream(path, table.schema) as writer:
            writer.write_table(table)
    else:
        with pa.ipc.new_file(path, table.schema) as writer:
            writer.write_table(table)


def _write_record_avro(
    rows: Iterable[Row], table_name: str, path: Path, batch_size: int
) -> None:
    fastavro = _require_fastavro()
    del batch_size
    data = list(rows)
    if not data:
        path.write_bytes(b"")
        return
    schema = {
        "name": table_name,
        "type": "record",
        "fields": [
            {"name": key, "type": ["null", _avro_type(value)], "default": None}
            for key, value in data[0].items()
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        fastavro.writer(stream, schema, data)


def _schema_sql(schemas: tuple[TableSchema, ...]) -> str:
    statements = [_create_table_sql(schema) for schema in schemas]
    for schema in schemas:
        for index_name, columns in schema.indexes:
            statements.append(
                f"CREATE INDEX {index_name} ON {schema.name} ({', '.join(columns)});"
            )
    return "\n\n".join(statements) + "\n\n"


def _create_table_sql(schema: TableSchema) -> str:
    foreign_keys = {
        foreign_key.column: foreign_key for foreign_key in schema.foreign_keys
    }
    lines: list[str] = []
    for column in schema.columns:
        parts = [column.name, column.sql_type]
        if not column.nullable:
            parts.append("NOT NULL")
        if schema.primary_key == (column.name,):
            parts.append("PRIMARY KEY")
        if column.unique:
            parts.append("UNIQUE")
        foreign_key = foreign_keys.get(column.name)
        if foreign_key is not None:
            parts.append(
                f"REFERENCES {foreign_key.target_table}({foreign_key.target_column})"
            )
            parts.append(f"ON DELETE {foreign_key.on_delete}")
        lines.append(" ".join(parts))
    if len(schema.primary_key) > 1:
        lines.append(f"PRIMARY KEY ({', '.join(schema.primary_key)})")
    rendered = ",\n    ".join(lines)
    return f"CREATE TABLE {schema.name} (\n    {rendered}\n);"


def _copy_line(schema: TableSchema, row: Row) -> str:
    values = (_copy_value(row.get(column)) for column in schema.column_names)
    return "\t".join(values) + "\n"


def _copy_value(value: object | None) -> str:
    if value is None:
        return r"\N"
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\t", r"\t")
        .replace("\n", r"\n")
        .replace("\r", r"\r")
    )


def _insert_tuple(schema: TableSchema, row: Row) -> str:
    values = (_sql_value(row.get(column)) for column in schema.column_names)
    return "(" + ", ".join(values) + ")"


def _sql_value(value: object | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _csv_value(value: object | None) -> object:
    return "" if value is None else value


def _column_from_value(name: str, value: object | None):
    from .schema import Column

    if isinstance(value, int):
        return Column(name, "INTEGER", nullable=True)
    if isinstance(value, float):
        return Column(name, "REAL", nullable=True)
    return Column(name, "TEXT", nullable=True)


def _avro_schema(schema: TableSchema) -> dict[str, object]:
    return {
        "name": schema.name,
        "type": "record",
        "fields": [
            {
                "name": column.name,
                "type": ["null", _avro_type_for_sql(column.sql_type)],
                "default": None,
            }
            for column in schema.columns
        ],
    }


def _avro_type_for_sql(sql_type: str) -> str:
    if sql_type == "INTEGER":
        return "long"
    if sql_type == "REAL":
        return "double"
    return "string"


def _avro_type(value: object | None) -> str:
    if isinstance(value, int):
        return "long"
    if isinstance(value, float):
        return "double"
    return "string"


def _record_table_name(model: type[BaseModel]) -> str:
    name = model.__name__
    chars: list[str] = []
    for index, character in enumerate(name):
        if character.isupper() and index:
            chars.append("_")
        chars.append(character.lower())
    snake = "".join(chars)
    return snake if snake.endswith("s") else f"{snake}s"


def _require_pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:  # pragma: no cover - exercised when absent
        raise ImportError(EXPORT_INSTALL_HINT) from error
    return pa, pq


def _require_fastavro():
    try:
        import fastavro
    except ImportError as error:  # pragma: no cover - exercised when absent
        raise ImportError(EXPORT_INSTALL_HINT) from error
    return fastavro
