# Fixture package

Public entry points are `load_config`, `FixtureConfig`, and `generate_fixtures`.
The CLI and library use the same pipeline. `exporters.read_bundle` reconstructs
portable outputs for caller-owned replay.

| Module | Responsibility |
| --- | --- |
| `types`, `config` | Strict configuration, import references and resolved paths. |
| `sources` | OpenAPI/Swagger normalization and Django/Pydantic model schemas. |
| `branches`, `adapters` | Revision-pinned generic branch catalogs. |
| `constraints`, `scenarios` | Bounded synthesis, validation and deduplication. |
| `runner` | Measurement receipts and coverage attribution. |
| `minimize` | Exact set cover within the measured candidate pool. |
| `codec`, `exporters` | Lossless typed JSON/CSV/SQLite bundles. |
| `provenance`, `pipeline` | Audit snapshots, stable replay and atomic publication. |

See the [user guide](../../../docs/fixtures/README.md) and
[runnable example](../../../examples/api_fixtures/README.md).
