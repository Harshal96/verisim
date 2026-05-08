# Contributing to Verisim

Thanks for helping improve Verisim. The project is still an early prototype, so
small, focused changes are easiest to review and keep stable.

## Development Setup

Clone the repository and install the development dependencies:

```bash
git clone https://github.com/Harshal96/verisim.git
cd verisim
uv sync --extra dev
```

Verisim targets Python 3.11 and newer. The package uses `uv` for local
development commands and dependency locking.

## Project Layout

- `src/verisim/`: package source.
- `examples/`: importable and runnable examples.
- `tests/`: pytest coverage for source and examples.
- `pyproject.toml`: package metadata, test settings, and tool configuration.
- `uv.lock`: locked dependency resolution.

## Local Checks

Run tests:

```bash
uv run --extra dev python -B -m pytest -q
```

Run the formatting and cleanup stack:

```bash
uv run --extra dev autoflake src examples tests
uv run --extra dev isort src examples tests
uv run --extra dev black src examples tests
```

Run linting:

```bash
uv run --extra dev ruff check src examples tests
```

Check formatting and cleanup without rewriting files:

```bash
uv run --extra dev autoflake --check src examples tests
uv run --extra dev isort --check-only src examples tests
uv run --extra dev black --check src examples tests
uv run --extra dev ruff check src examples tests
```

Run the coverage gate:

```bash
uv run --extra dev python -B -m coverage run -m pytest -q
uv run --extra dev python -B -m coverage report --fail-under=100
```

## Code Style

- Keep generated data deterministic when a seed is provided.
- Prefer Pydantic models and typed context over unstructured dictionaries.
- Keep the core package offline by default. AI adapters, external data, and
  networked behavior should remain optional and replaceable.
- Preserve non-routable synthetic contact details unless a feature explicitly
  requires different safe test data.
- Add or update tests when changing behavior.

## Pull Requests

Before opening a pull request:

1. Keep the change focused on one behavior, fix, or documentation update.
2. Update examples or README snippets when public usage changes.
3. Run the relevant local checks from this guide.
4. Include a short summary and the verification commands you ran.

For larger changes, open an issue or draft PR first so the design can be shaped
before implementation gets too far ahead.
