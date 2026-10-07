# Core generation

[Project overview](../../README.md) · [Runnable examples](../../examples/README.md)

The shared generation engine lives in [api.py](api.py), with domain models in
[models.py](models.py) and dependency-aware providers in [providers.py](providers.py)
and [domain_providers.py](domain_providers.py).

- [Quickstart](#quickstart)
- [Core ideas](#core-ideas)
- [Command line usage](#command-line-usage)
- [Related datasets](#generate-related-datasets)
- [Existing context](#use-existing-context)
- [Schema inference](#infer-providers-from-existing-schemas)
- [Statistical profiles](#control-statistical-shape)
- [Testing and QA](#testing-and-qa-modes)
- [Activity streams](#activity-streams)
- [Optional dependencies](#optional-dependencies)

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
Industry + founded_year -> CompanyRecord
CompanyRecord -> Company + Contact + Job
Person + Job + Company -> Socials
Person + Job + Company -> Bio
Person + Address + Contact + Job + Company + Socials -> PersonRecord
PersonRecord + ProductRecord -> OrderRecord
PersonRecord + Company -> TransactionRecord
PersonRecord + Company -> EventRecord / SupportTicketRecord
PersonRecord + ProductRecord -> ReviewRecord
PersonRecord + Company -> MedicalRecord
```

**Safe by default**

Generated contact details are non-routable by default. Emails, websites, and
avatar URLs use synthetic `.example.invalid` domains, preserving realistic local
parts, hosts, formats, and relationships. When a person is generated with
company context, their email uses the company's domain and email pattern.

**Deterministic seeded output**

Passing `seed=` makes generation reproducible, including UUID primary keys.
Reusing the same locale, seed, and generation order will reproduce the same
IDs. Treat seeded UUIDs as synthetic fixture identifiers only; do not use them
as secrets, authorization tokens, or production identifiers.

## Supported Models

- Pydantic v2 domain models for `PersonRecord`, `CompanyRecord`,
  `ProductRecord`, `OrderRecord`, `TransactionRecord`, `EventRecord`,
  `SupportTicketRecord`, `ReviewRecord`, `MedicalRecord`, `Person`,
  `Address`, `Contact`, `PhoneNumber`, `Job`, `Company`, `Product`,
  `Socials`, `Website`, and datasets.

A per-run uniqueness registry tracks IDs, usernames, emails, phones, companies,
and social handles. See [registry.py](registry.py).

## Command Line Usage

Verisim also installs a Faker-inspired CLI:

```bash
verisim [OPTIONS] COMMAND [ARGS]...
```

Generate one coherent person record:

```bash
uv run verisim person-record --seed 123
```

Generate repeated records as JSON lines:

```bash
uv run verisim person-record -r 3 --locale en_US --seed 123
```

Generate another supported target:

```bash
uv run verisim company-record --locale en_US --indent 2
uv run verisim order-record --seed 123 --indent 2
uv run verisim transaction-record --seed 123 --indent 2
```

First-class record targets include `person-record`, `company-record`,
`product-record`, `order-record`, `transaction-record`, `event-record`,
`support-ticket-record`, `review-record`, and `medical-record`.

Write output to a file:

```bash
uv run verisim person-record --repeat 10 --output people.jsonl
```

Additional targets include `person`, `company`, `product`, `address`, `contact`,
`job`, `socials`, and `website`.

Example shape:

```python
{
    "person": {
        "name": "Brooke Garcia",
        "username": "brooke.garcia"
    },
    "contact": {
        "email": "brooke.garcia@kindred-medical-group.example.invalid",
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

## Generate Related Datasets

Verisim can generate coherent datasets with people assigned to generated
company records:

```python
from verisim import DatasetSpec, Verisim

v = Verisim(seed=7)
dataset = v.dataset(
    DatasetSpec(
        companies=3,
        people_per_company={"seed": 8, "startup": 25, "mid-market": 120},
    )
)

assert dataset.people[0].company.id in {company.id for company in dataset.companies}
```

The dataset path uses the same context-aware providers as single-record
generation, so uniqueness, email domains, job industries, company size bands,
and department distribution are preserved.

```bash
uv run verisim dataset --people 40 --companies 6 --seed 7 --indent 2
```

For streaming generation and file formats, see the [export guide](exporters/README.md).

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

Company context works the same way across calls:

```python
from verisim import CompanyRecord, PersonRecord, Verisim

v = Verisim(seed=7)
company = v.generate(CompanyRecord, context={"size_band": "startup"})
employee = v.generate(PersonRecord, context={"company": company})

assert employee.contact.email.endswith(f"@{company.domain}")
assert employee.job.department in company.departments
```

Conflict modes:

- `strict`: raise when supplied context contradicts model invariants.
- `repair`: keep valid context and regenerate dependent conflicting fields.
- `explain`: return diagnostics without generating a replacement record.

## Infer Providers From Existing Schemas

Infer provider intent from an existing schema:

```python
from pydantic import BaseModel

from verisim import Verisim, generate_from_schema, infer_providers


class Customer(BaseModel):
    email: str
    first_name: str
    company_name: str


plan = infer_providers(Customer)
record = Verisim(seed=7).generate(Customer)

payload = generate_from_schema(
    {
        "type": "object",
        "required": ["email"],
        "properties": {"email": {"type": "string", "format": "email"}},
    },
    seed=7,
)
```

## Control Statistical Shape

Verisim profiles let generated records keep coherent context while moving away
from uniform random choices. Profiles can weight categorical values, draw
bounded normal or Pareto-shaped values, bias datetimes toward weekdays, apply
conditional rules, and set null rates for nullable fields.

```python
from verisim import (
    ConditionalRule,
    DatasetSpec,
    FieldRule,
    NormalInt,
    ParetoInt,
    PersonRecord,
    Predicate,
    StatisticalProfile,
    Verisim,
    WeightedChoice,
)

profile = StatisticalProfile(
    fields={
        "person.age": FieldRule(
            distribution=NormalInt(mean=38, stdev=12, minimum=18, maximum=80)
        ),
        "company.size_band": FieldRule(
            distribution=WeightedChoice(
                values={"startup": 5, "SMB": 8, "mid-market": 4, "enterprise": 1}
            )
        ),
        "company.employee_count": FieldRule(
            distribution=ParetoInt(minimum=2, shape=1.4, maximum=10_000)
        ),
        "company.address": FieldRule(null_rate=0.15),
    },
    correlations=[
        ConditionalRule(
            when=[Predicate(path="person.age", op="lte", value=25)],
            apply={
                "job.level": FieldRule(
                    distribution=WeightedChoice(values={"Junior": 8, "Senior": 1})
                )
            },
        )
    ],
)

v = Verisim(seed=42, profile=profile)
record = v.generate(PersonRecord)
dataset = v.dataset(DatasetSpec(people=100, companies=5, profile=profile))
```

Explicit context still wins over profile rules. For example,
`context={"size_band": "startup"}` keeps the requested company size even when a
profile weights other size bands. Null rates are validated before generation and
are accepted only for nullable fields such as `Company.address`.

Profiles also work with user-defined Pydantic models. Register lightweight
field resolvers for semantic fields Verisim cannot infer, and use profile rules
for the statistical parts:

```python
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from verisim import DateTimeWindow, FieldContext, FieldRule, StatisticalProfile


class AuditEvent(BaseModel):
    id: UUID
    amount: int
    created_at: datetime


class AuditResolver:
    def resolve(self, context: FieldContext) -> object:
        if context.path == "id":
            return UUID("00000000-0000-0000-0000-000000000123")
        return context.unresolved


profile = StatisticalProfile(
    fields={
        "created_at": FieldRule(
            distribution=DateTimeWindow(
                start=datetime(2026, 5, 18, 9, tzinfo=UTC),
                end=datetime(2026, 5, 22, 17, tzinfo=UTC),
                weekday_weights={0: 1, 1: 1, 2: 1, 3: 1, 4: 1},
            )
        )
    }
)

event = Verisim(seed=7, profile=profile, resolvers=[AuditResolver()]).generate(
    AuditEvent
)
```

## Testing And QA Modes

Verisim can generate fixtures for validation, parser, and deduplication tests
without leaving the Pydantic-object contract.

```python
from pydantic import ValidationError

from verisim import DatasetSpec, PersonRecord, Verisim

v = Verisim(seed=42)

edge_record = v.generate(PersonRecord, mode="edge_cases", edge_case="nul")

try:
    v.generate(PersonRecord, mode="schema_violations", violation="contact.email")
except ValidationError:
    # Pydantic raises a validation error for the intentionally invalid payload.
    pass

dataset = v.dataset(
    DatasetSpec(
        people=100,
        companies=10,
        people_duplicate_percent=10,
    )
)
```

`mode="edge_cases"` returns valid model instances with boundary values such as
empty strings, long strings, null bytes, right-to-left text, negative
coordinates, and epoch-zero dates. `mode="schema_violations"` builds an invalid
payload from a valid record and raises a Pydantic validation error; it never
returns an invalid model instance.

Duplicate injection keeps the requested total count fixed. For example,
`people=100` with `people_duplicate_percent=10` returns 100 people, including 10
same-ID near duplicates. JSON and CSV exports preserve those rows. SQL and
SQLite exports may fail on primary-key or unique constraints, which is useful
when testing constraint handling.

The same options are available from the CLI:

```bash
uv run verisim person-record --mode edge_cases --edge-case rtl --seed 42
uv run verisim dataset --people 100 --companies 10 --people-duplicate-percent 10
```

## Activity Streams

Generate a chronological activity stream for synthetic people:

```bash
uv run verisim activity-stream --people 10 --events-per-person 100 --seed 7
uv run verisim activity-stream --people 10 --events-per-person 100 --sink jsonl --output activity.jsonl --throughput 250
```

Activity stream events are emitted as JSON lines with a stable envelope
containing schema version, global sequence, per-person sequence, actor,
timestamp, activity kind, session id, and a typed payload. Supported activity
kinds are `login`, `purchase`, and `support_ticket`.

Kafka output is available through the optional Kafka extra:

```bash
uv add "verisim[kafka]"
uv run verisim activity-stream --sink kafka --bootstrap-servers localhost:9092 --topic activity-events --throughput 500
```

## Optional Dependencies

The core package remains offline and deterministic. External services are
opt-in and caller-owned.

| Extra | Purpose | Guide |
| --- | --- | --- |
| `lite` | Built-in locale and country data; no extra dependencies. | [Data packs](datasets/README.md) |
| `full` | Expanded data pack, currently adding Spain; no extra dependencies. | [Data packs](datasets/README.md) |
| `ai` | Offline training datasets and an adapter protocol; no extra dependencies. | [AI training](ai_training/README.md) |
| `export` | PyArrow and fastavro for Parquet, Feather/Arrow, and Avro. | [Exports](exporters/README.md) |
| `fixtures` | PyYAML for YAML fixture configuration; JSON needs no extra dependencies. | [API fixtures](fixtures/README.md) |
| `masking` | pandas for tabular PII masking. | [Masking](masking/README.md) |
| `sqlalchemy`, `django`, `pytest` | Framework-specific factories and fixtures. | [Integrations](integrations/README.md) |
| `kafka` | confluent-kafka for activity output. | [Activity streams](#activity-streams) |

For example, install export dependencies with `uv add "verisim[export]"`.
For local setup, tests, formatting, lint, and coverage commands, see
[CONTRIBUTING.md](../../CONTRIBUTING.md).
