# Verisim

Context-aware synthetic data for Python. The name comes from “verisimilitude,”
meaning “the appearance of being real.”

Verisim generates coherent Pydantic domain objects with shared context. A
person's name, username, email, address, job, company, and bio fit together,
making the data useful for demos, seed data, tests, and synthetic datasets.
Generation runs offline by default, supports reproducible seeds, and uses
non-routable synthetic contact details.

**Status:** early prototype (alpha). See the feature guides below for usage and
current limits.

## Install

Requires Python 3.11 or newer.

```bash
uv add verisim
# Or:
python -m pip install verisim
```

## Quickstart

```python
from verisim import PersonRecord, Verisim

record = Verisim(locale="en_US", seed=123).generate(PersonRecord)

print(record.person.name)
print(record.contact.email)
print(record.model_dump_json())
```

```bash
verisim person-record --seed 123
```

## Feature Guides

| Feature | README |
| --- | --- |
| Core models, context, related datasets, schema inference, statistical profiles, QA modes, CLI, and activity streams | [Core generation](src/verisim/README.md) |
| JSON/JSONL, CSV, SQL, SQLite, Parquet, Arrow, Avro, and schema contracts | [Exports](src/verisim/exporters/README.md) |
| Locale, script, lite/full data packs, and data provenance | [Data packs](src/verisim/datasets/README.md) |
| Coherent replacements for existing tabular PII | [Masking](src/verisim/masking/README.md) |
| SQLAlchemy, Django, and pytest factories and fixtures | [Framework integrations](src/verisim/integrations/README.md) |
| Offline instruction pairs, classification, NER, chat datasets, and custom adapters | [AI training](src/verisim/ai_training/README.md) |
| Measured API branch scenarios and replayable fixture bundles | [API fixtures](src/verisim/fixtures/README.md) |
| Runnable examples and a comparison with independent random fields | [Examples](examples/README.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for source setup and local checks,
[CHANGELOG.md](CHANGELOG.md) for changes, and [RELEASING.md](RELEASING.md) for
release instructions.

## License

[MIT](LICENSE).
