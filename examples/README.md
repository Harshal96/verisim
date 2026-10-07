# Examples

Run examples from the repository root after `uv sync --extra dev`:

```bash
uv run python -m examples.basic_person
uv run python -m examples.order_record
uv run python -m examples.dataset_generation
```

The record examples cover coherent people, companies, products, orders,
transactions, events, reviews, support tickets and medical records.
`context_repair.py` demonstrates repair of partially supplied context, and
`ai_training.py` demonstrates synthetic training pairs.

The [API fixtures example](api_fixtures/README.md) adds Swagger/OpenAPI and
Django/Pydantic inputs, real measured branch coverage, exact scenario selection,
replay verification, and JSON/CSV/SQLite exports. It includes its own configuration,
catalog, models and runner.
