# Runnable API fixture example

This small Django application uses Pydantic request models and an in-memory
SQLite database. Its caller-owned runner uses Coverage.py to observe real
source arcs around exactly one invocation, then clears the database. The catalog
lists both outcomes of five business decisions in `api.py`.

From the repository root:

```bash
uv sync --extra dev --extra fixtures
uv run --frozen verisim fixtures --config examples/api_fixtures/fixtures.json
uv run --frozen verisim fixtures --config examples/api_fixtures/fixtures.json \
  --format csv --output out/fixtures.csv
uv run --frozen verisim fixtures --config examples/api_fixtures/fixtures.json \
  --format sqlite --output out/fixtures.sqlite
```

Output paths are relative to this example's project root. Each invocation emits
one JSON manifest; bundles and reports appear in `examples/api_fixtures/out/`.
The result selects six scenarios covering ten declared arcs and independently
replays them. Outcomes include created, invalid quantity, denied actor,
unavailable inventory, missing customer, and inactive customer.

| File | Purpose |
| --- | --- |
| `fixtures.json` | Full runnable configuration and optional candidate seeds. |
| `openapi.json` | OpenAPI 3.1 operation contract. |
| `models.py`, `schemas.py`, `settings.py` | Django state and Pydantic payload. |
| `api.py` | The business code measured by the runner. |
| `branches.json` | Revision-pinned catalog with real line transitions. |
| `support.py` | Baseline isolation, persistence, coverage, checks and cleanup. |

The catalog's line numbers must be refreshed if `api.py` changes. This example
demonstrates local integration; it does not connect to your internal graph.
For FastAPI, replace the invocation with your ASGI test client, retaining the
same runner receipt and isolation rules.

See the [fixture API guide](../../docs/fixtures/README.md) for the full contracts.
