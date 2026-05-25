# Verisim

Context-aware synthetic data for Python.

The name comes from "verisimilitude," meaning "the appearance of being real."

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

Here is what that looks like in practice:

<table>
<thead>
<tr>
<th>Faker: plausible fields, isolated from each other</th>
<th>Verisim: one generated person, shared context</th>
</tr>
</thead>
<tbody>
<tr>
<td>
<pre lang="python"><code>from faker import Faker

fake = Faker("en_US")

person = {
    "name": fake.name(),
    "username": fake.user_name(),
    "email": fake.email(),
    "phone": fake.phone_number(),
    "address": fake.address(),
    "job": fake.job(),
    "company": fake.company(),
    "bio": fake.sentence(),
    "website": fake.url(),
}</code></pre>
</td>
<td>
<pre lang="python"><code>from verisim import PersonRecord, Verisim

v = Verisim(locale="en_US", seed=123)
record = v.generate(PersonRecord)

person = {
    "name": record.person.name,
    "username": record.person.username,
    "email": record.contact.email,
    "phone": record.contact.phone.e164,
    "address": (
        f"{record.address.city}, "
        f"{record.address.region_code} "
        f"{record.address.postal_code}"
    ),
    "job": record.job.title,
    "company": record.company.name,
    "bio": record.bio,
    "website": record.website.url,
}</code></pre>
</td>
</tr>
<tr>
<td>
<pre lang="json"><code>{
  "name": "Maya Rao",
  "username": "thomas77",
  "email": "melissa.watson@example.net",
  "phone": "+1-202-555-0188",
  "address": "4896 James Station\nPhoenix, AZ 85004",
  "job": "Marine scientist",
  "company": "Northstar Medical Group",
  "bio": "Writes about fintech compliance.",
  "website": "https://miller-johnson.example.org/"
}</code></pre>
<p>Each value is believable alone. Together, it is a person whose name, login, inbox, job, company, bio, and website all point in different directions.</p>
</td>
<td>
<pre lang="json"><code>{
  "name": "Brooke Garcia",
  "username": "brooke.garcia",
  "email": "brooke.garcia@kindred-medical-group.example.invalid",
  "phone": "+14155550000",
  "address": "San Francisco, CA 94107",
  "job": "Product Manager",
  "company": "Kindred Medical Group",
  "bio": "Brooke Garcia works as a Product Manager at Kindred Medical Group...",
  "website": "https://brooke.garcia.example.invalid"
}</code></pre>
<p>The same facts carry through the record: name to username, email, website, city-aware contact data, company, job, and bio.</p>
</td>
</tr>
</tbody>
</table>

Verisim treats fake data as a domain modeling problem. It generates an aggregate
record through a dependency-aware context graph, so later fields can use facts
from earlier fields. Address generation knows about country, region, city, and
postal code. Contact generation knows about the address country. Social
generation knows about the person, job, and company. Bio generation knows about
the job and industry. Company records carry their own scale, legal form,
departments, leadership, domains, and email pattern, and those facts propagate
when generating people for that company.

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
uv add "verisim[export]"
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

Generate a coherent dataset:

```bash
uv run verisim dataset --people 40 --companies 6 --seed 7 --indent 2
```

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

Write output to a file:

```bash
uv run verisim person-record --repeat 10 --output people.jsonl
```

Supported record commands are `person-record`, `person`, `company-record`,
`company`, `product-record`, `product`, `address`, `contact`, `job`, `socials`,
and `website`.

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

Generated contact details are non-routable by default. Emails and websites use
synthetic `.example.invalid` domains, while still preserving realistic local
parts, hosts, formats, and relationships. When a person is generated with
company context, their email uses the company's domain and email pattern.

**Deterministic seeded output**

Passing `seed=` makes generation reproducible, including UUID primary keys.
Reusing the same locale, seed, and generation order will reproduce the same
IDs. Treat seeded UUIDs as synthetic fixture identifiers only; do not use them
as secrets, authorization tokens, or production identifiers.

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

## Mask Existing PII

The `verisim[masking]` extra can mask direct identifiers in existing tabular
data. It detects likely person, email, phone, and address columns, then replaces
each real identity with a coherent synthetic `PersonRecord`. Reusing a
`MaskingSession` preserves mappings across multiple DataFrames or SQL tables
within the same run, so repeated emails and related rows keep joining.

```python
import pandas as pd

from verisim import MaskingConfig, MaskingSession, mask_dataframe

df = pd.DataFrame(
    [
        {"name": "Alice Adams", "email": "alice@company.com", "city": "Chicago"},
        {"name": "Alice Adams", "email": "alice@company.com", "city": "Chicago"},
    ]
)

session = MaskingSession(MaskingConfig(seed=42))
masked = mask_dataframe(df, session=session).data
```

For DB-API connections, `mask_sql_table()` creates a masked destination table
and leaves the source table untouched. The v1 write path is SQLite-tested and
uses simple validated table identifiers.

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

## Locale And Script

Locale describes the cultural/data origin. Output language and script are
separate knobs.

```python
from verisim import PersonRecord, Verisim

v = Verisim(locale="en_IN", output_language="en", script="latin", seed=13)
record = v.generate(PersonRecord)

print(record.person.name)
print(record.address.country_code)
print(record.contact.phone.e164)
```

This supports Indian names in Latin script, such as `Rakesh`, `Om`, or
`Prakash`, while keeping address and phone fields country-aware.

The lite pack includes US, UK, Canadian, Australian, Indian, German, Mexican,
Japanese, French, Brazilian, and Chinese coverage. The packaged locale codes
are `en_US`, `en_GB`, `en_CA`, `en_AU`, `en_IN`, `hi_IN`, `de_DE`, `es_MX`,
`ja_JP`, `fr_FR`, `pt_BR`, and `zh_CN`; each includes 1,000 given names and
1,000 family names.

Country address data for `US`, `GB`, `CA`, `AU`, `IN`, `DE`, `MX`, `JP`, `FR`,
`BR`, and `CN` is generated from open
[GeoNames postal-code archives](https://download.geonames.org/export/zip/) with
Verisim-authored synthetic street names and suffixes. The packaged data
currently contains 53 US regions, 6 UK regions, 13 Canadian regions, 8
Australian regions, 35 Indian regions, 33 German regions, 32 Mexican regions,
47 Japanese regions, 14 French regions, 27 Brazilian regions, and 35 Chinese
regions, covering more than 3.3 million postal-code-to-city relationships.
Canada and the UK use the GeoNames full-code archives; the standard GeoNames
country ZIPs are used for the other supported countries. The source data is
useful for coherent synthetic generation, not postal authority validation.

To refresh the packaged country JSON files from GeoNames:

```bash
uv run python scripts/build_country_datasets.py --download
```

The refresh script downloads archives over HTTPS and verifies each source
archive against the pinned SHA-256 manifest before rebuilding packaged JSON.

## Current Features

- Pydantic v2 domain models for `PersonRecord`, `CompanyRecord`,
  `ProductRecord`, `OrderRecord`, `TransactionRecord`, `EventRecord`,
  `SupportTicketRecord`, `ReviewRecord`, `MedicalRecord`, `Person`,
  `Address`, `Contact`, `PhoneNumber`, `Job`, `Company`, `Product`,
  `Socials`, `Website`, and datasets.
- Context graph provider engine.
- Per-run uniqueness registry for IDs, usernames, emails, phones, companies,
  and social handles.
- Lite data pack with US, UK, Canada, Australia, India, and Germany sample
  support.
- Non-routable synthetic emails, websites, and avatar URLs.
- Consistency-preserving PII masking for pandas DataFrames and DB-API SQL table
  copies.
- Strict, repair, and explain modes for existing context.
- Importable and runnable `examples` package.
- 90%+ measured coverage across `src/verisim` and `examples`.

## Package Shape

The package declares extras for the intended product tiers:

```bash
verisim[lite]
verisim[full]
verisim[ai]
verisim[export]
```

Current state:

- `lite`: implemented as the built-in data pack.
- `full`: reserved for large regional/global data packs.
- `ai`: reserved for optional prose-generation adapters.
- `export`: enables PyArrow and fastavro writers for Parquet, Feather/Arrow,
  and Avro.

The core package remains offline and deterministic. AI or external data should
be opt-in, auditable, and replaceable.

## Examples

Run the included examples:

```bash
uv run python -m examples.basic_person
uv run python -m examples.company_record
uv run python -m examples.context_repair
uv run python -m examples.dataset_generation
uv run python -m examples.product_record
```

Import them from Python:

```python
from examples import (
    basic_person,
    company_record,
    context_repair,
    dataset_generation,
    product_record,
)

record = basic_person.generate_example(seed=123)
company = company_record.generate_example(seed=123, size_band="startup")
diagnostics, repaired = context_repair.generate_example(seed=123)
dataset = dataset_generation.generate_example(seed=123, people=5, companies=2)
product = product_record.generate_example(seed=123)
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full local development and pull
request workflow.

Run tests:

```bash
uv run --extra dev python -B -m pytest -q
```

Format and sort imports:

```bash
uv run --extra dev autoflake src examples tests
uv run --extra dev isort src examples tests
uv run --extra dev black src examples tests
```

Lint:

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

Run the 100% per-file coverage gate:

```bash
uv run --extra dev python -B -m coverage run -m pytest -q
uv run --extra dev python -B -m coverage report --fail-under=100
```

## Roadmap

TBD.

## License

See [LICENSE](LICENSE).
