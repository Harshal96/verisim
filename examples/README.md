# Examples

[Project overview](../README.md) · [Core generation guide](../src/verisim/README.md)

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

## Run and Import Examples

Run the included examples:

```bash
uv run python -m examples.basic_person
uv run python -m examples.company_record
uv run python -m examples.context_repair
uv run python -m examples.dataset_generation
uv run python -m examples.product_record
uv run python -m examples.ai_training
```

Import them from Python:

```python
from examples import (
    ai_training,
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
ai_datasets = ai_training.generate_example(seed=123, count=2)
```

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
