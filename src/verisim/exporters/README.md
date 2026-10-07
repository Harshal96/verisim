# Dataset and schema exports

[Project overview](../../../README.md) · [Core generation](../README.md)

The export package writes coherent records and related datasets. See
[core.py](core.py) for writers, [projectors.py](projectors.py) for table layouts,
and [json_schema.py](json_schema.py) for schema contracts.

## Streaming Related Datasets

Large dataset exports can stream from `iter_dataset()` without building a full
`Dataset` in memory:

```python
from pathlib import Path

from verisim import DatasetSpec, Verisim, export_dataset

v = Verisim(seed=7)
events = v.iter_dataset(DatasetSpec(people=1_000_000, companies=5_000, products=20_000))

export_dataset(events, "sql", Path("dataset.sql"), layout="both", sql_mode="copy")
```

`export_dataset()` supports nested JSON for materialized datasets, event JSONL,
relational CSV directories, SQL dumps, SQLite databases, Parquet, Feather/Arrow
IPC, and Avro. Relational exports use `companies`, `people`, `products`,
`product_plans`, `social_accounts`, and `export_metadata`; wide exports use
`people_wide` and `products_wide` joined with company fields. SQL defaults to a
Postgres-friendly `COPY ... FROM stdin` dump, with `sql_mode="insert"` available
for portable `INSERT` statements.

## Command Line Exports

Export a coherent dataset in relational, wide, or combined layouts:

```bash
uv run verisim dataset --people 40 --companies 6 --products 12 --seed 7 --format csv --layout both --output dataset_tables/
uv run verisim dataset --people 40 --companies 6 --products 12 --seed 7 --format sql --sql-mode copy --output dataset.sql
uv run verisim dataset --people 40 --companies 6 --products 12 --seed 7 --format sqlite --output dataset.sqlite
```

The `verisim[export]` extra enables Parquet, Arrow/Feather, and Avro:

```bash
uv add "verisim[export]"
uv run verisim dataset --people 1000000 --companies 5000 --format parquet --layout relational --output dataset_parquet/
uv run verisim person-record --repeat 1000000 --format parquet --output people.parquet
```

JSON, JSONL, CSV, SQL, and SQLite are available without the export extra. Add
`verisim[export]` for Parquet, Arrow/Feather, and Avro. For single-record CLI
commands and JSONL output, see [command line usage](../README.md#command-line-usage).

## Export Schema Contracts

Export a synthetic data contract:

```python
from verisim import PersonRecord, export_json_schema

schema = export_json_schema(PersonRecord)
```

```bash
uv run verisim schema person-record --output person.schema.json
uv run verisim schema person-record --dialect openapi-3.1 --output openapi.json
```

See [dataset_generation.py](../../../examples/dataset_generation.py) for a
runnable dataset example. API fixture bundles have their own codec and export
pipeline; see the [fixture guide](../fixtures/README.md).
