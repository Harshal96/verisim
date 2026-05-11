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
```

Generate a coherent dataset:

```bash
uv run verisim dataset --people 40 --companies 6 --seed 7 --indent 2
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
  `ProductRecord`, `Person`, `Address`, `Contact`, `PhoneNumber`, `Job`,
  `Company`, `Product`, `Socials`, `Website`, and datasets.
- Context graph provider engine.
- Per-run uniqueness registry for IDs, usernames, emails, phones, companies,
  and social handles.
- Lite data pack with US, UK, Canada, Australia, India, and Germany sample
  support.
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
