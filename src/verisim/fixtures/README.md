# Fixture package

[Project overview](../../../README.md) · [Core generation](../README.md)

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

## Command Line Usage

Generate a portable API fixture bundle from OpenAPI, Django/Pydantic models,
and a caller-owned branch catalog and test runner:

```bash
uv add 'verisim[fixtures,django]'
verisim fixtures --config fixtures.yaml --format sqlite --output ./out/fixtures.sqlite
```

The config example and generic catalog contract are in
[the fixture API guide](../../../docs/fixtures/README.md) and the
[runnable example](../../../examples/api_fixtures/README.md). The configured
branch adapter returns operation-scoped target IDs; the runner performs one
isolated measured API invocation per candidate and returns observed IDs. The
exact optimizer chooses the fewest replayable scenarios within that finite,
measured candidate pool. A successful bundle is published only after complete
declared-scope coverage, an optimality proof within the pool, and replay
verification. Its JSON process manifest keeps coverage, optimization, replay,
and application checks independent. SQLite is a portable bundle format, not an
application database or Django fixture file.
