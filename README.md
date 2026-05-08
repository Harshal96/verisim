# Verisim

Context-aware synthetic data for Python.

Verisim generates whole, coherent Pydantic domain objects instead of unrelated
random fields. A generated person can have a name, username, email, phone,
address, job, company, bio, website, and social profiles that all make sense
together.

> Project status: early prototype. The current package includes the core engine,
> Pydantic models, a lite data pack, examples, and full test coverage. Large
> global data packs and AI prose adapters are extension points, not finished
> product features yet.

## Why Verisim Exists

Libraries like Faker are excellent at generating individual fake values. The
problem starts when those values need to belong to the same fictional person,
company, or dataset.

Typical generated records often look fake because each field is created in
isolation:

- the name and username do not belong together,
- the bio has nothing to do with the job,
- the phone number does not match the country,
- the website domain is unrelated to the person or company,
- every social profile reuses the same handle,
- the address may look formatted but not geographically coherent.

Verisim treats fake data as a domain modeling problem. It generates an aggregate
record through a dependency-aware context graph, so later fields can use facts
from earlier fields. Address generation knows about country, region, city, and
postal code. Contact generation knows about the address country. Social
generation knows about the person, job, and company. Bio generation knows about
the job and industry.

The result is synthetic data that is still safe and fake, but believable enough
for demos, seed data, tests, prototypes, and synthetic datasets.

## Install

Install from PyPI with `uv`:

```bash
uv add verisim
```

Or install with `pip`:

```bash
python -m pip install verisim
```

Install optional package tiers as they become available:

```bash
uv add "verisim[lite]"
uv add "verisim[full]"
uv add "verisim[ai]"
```

## Development From Source

Clone the repository and install the development dependencies:

```bash
git clone https://github.com/Harshal96/verisim.git
cd verisim
uv sync --extra dev
```

For editable installs while working on Verisim from another local project, use
a relative path to your clone:

```bash
uv add --editable ../verisim
```

## Quickstart

```python
from verisim import PersonRecord, Verisim

verisim = Verisim(locale="en_US", output_language="en", seed=123)
record = verisim.generate(PersonRecord)

print(record.person.name)
print(record.person.username)
print(record.contact.email)
print(record.contact.phone.e164)
print(record.address.city, record.address.region_code, record.address.postal_code)
print(record.job.title)
print(record.company.name)
print(record.bio)
print(record.model_dump_json())
```

Example shape:

```python
{
    "person": {
        "name": "Brooke Garcia",
        "username": "brooke.garcia"
    },
    "contact": {
        "email": "brooke.garcia@san-francisco.example.invalid",
        "phone": {
            "e164": "+14155550000",
            "country_code": "US"
        }
    },
    "address": {
        "city": "San Francisco",
        "region_code": "CA",
        "postal_code": "94107",
        "country_code": "US"
    },
    "job": {
        "title": "Product Manager",
        "industry": "Healthcare Technology"
    },
    "company": {
        "name": "Kindred Medical Group",
        "industry": "Healthcare Technology"
    },
    "bio": "Brooke Garcia works as a Product Manager at Kindred Medical Group..."
}
```

## Core Ideas

**Model-first API**

Verisim is used through Pydantic models:

```python
from verisim import PersonRecord, Socials, Verisim

v = Verisim(seed=42)

person = v.generate(PersonRecord)
socials = v.generate(Socials, context=person)
```

JSON output comes from Pydantic:

```python
payload = person.model_dump_json()
```

**Context graph generation**

Providers declare what they need and what they produce. Verisim resolves the
graph, shares typed context between providers, and validates the generated
result.

```text
Address -> Contact
Person + Address -> Contact
Person + Job + Company -> Socials
Person + Job + Company -> Bio
Person + Address + Contact + Job + Company + Socials -> PersonRecord
```

**Safe by default**

Generated contact details are non-routable by default. Emails and websites use
synthetic `.example.invalid` domains, while still preserving realistic local
parts, hosts, formats, and relationships.

## Generate Related Datasets

Verisim can generate a small coherent dataset with people assigned to generated
companies:

```python
from verisim import DatasetSpec, Verisim

v = Verisim(seed=7)
dataset = v.dataset(DatasetSpec(people=40, companies=6))

assert dataset.people[0].company.id in {company.id for company in dataset.companies}
```

The dataset path uses the same context-aware providers as single-record
generation, so uniqueness and domain consistency are preserved.

## Use Existing Context

You can provide context and ask Verisim to generate the rest:

```python
from verisim import Address, PersonRecord, Verisim

v = Verisim(seed=1)

address = Address(
    line1="19 Birch Street",
    city="Austin",
    region="Texas",
    region_code="TX",
    postal_code="78701",
    country="United States",
    country_code="US",
)

record = v.generate(PersonRecord, context={"address": address}, mode="repair")
```

Conflict modes:

- `strict`: raise when supplied context contradicts model invariants.
- `repair`: keep valid context and regenerate dependent conflicting fields.
- `explain`: return diagnostics without generating a replacement record.

## Locale And Script

Locale describes the cultural/data origin. Output language and script are
separate knobs.

```python
from verisim import PersonRecord, Verisim

v = Verisim(locale="hi_IN", output_language="en", script="latin", seed=13)
record = v.generate(PersonRecord)

print(record.person.name)
print(record.address.country_code)
print(record.contact.phone.e164)
```

This supports Indian names in Latin script, such as `Rakesh`, `Om`, or
`Prakash`, while keeping address and phone fields country-aware.

## Current Features

- Pydantic v2 domain models for `PersonRecord`, `Person`, `Address`, `Contact`,
  `PhoneNumber`, `Job`, `Company`, `Socials`, `Website`, and datasets.
- Context graph provider engine.
- Per-run uniqueness registry for IDs, usernames, emails, phones, companies,
  and social handles.
- Lite data pack with US English generation and priority-country sample support.
- Non-routable synthetic emails, websites, and avatar URLs.
- Strict, repair, and explain modes for existing context.
- Importable and runnable `examples` package.
- 100% measured coverage across `src/verisim` and `examples`.

## Package Shape

The package declares extras for the intended product tiers:

```bash
verisim[lite]
verisim[full]
verisim[ai]
```

Current state:

- `lite`: implemented as the built-in data pack.
- `full`: reserved for large regional/global data packs.
- `ai`: reserved for optional prose-generation adapters.

The core package remains offline and deterministic. AI or external data should
be opt-in, auditable, and replaceable.

## Examples

Run the included examples:

```bash
uv run python -m examples.basic_person
uv run python -m examples.context_repair
uv run python -m examples.dataset_generation
```

Import them from Python:

```python
from examples import basic_person, context_repair, dataset_generation

record = basic_person.generate_example(seed=123)
diagnostics, repaired = context_repair.generate_example(seed=123)
dataset = dataset_generation.generate_example(seed=123, people=5, companies=2)
```

## Development

Run tests:

```bash
uv run --extra dev python -B -m pytest -q
```

Run the 100% per-file coverage gate:

```bash
uv run --extra dev python -B -m coverage run -m pytest -q
uv run --extra dev python -B -m coverage report --fail-under=100
```

## Roadmap

TBD.

## License

See [LICENSE](LICENSE).
