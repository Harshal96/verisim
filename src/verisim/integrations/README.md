# Framework Integrations

[Verisim overview](../../../README.md) · [Package guide](../README.md)

Install only the integration dependencies you need:

```bash
uv add "verisim[sqlalchemy]"
uv add "verisim[django]"
uv add "verisim[pytest]"
```

SQLAlchemy factories inspect mapped classes and return unsaved instances ready
for `session.add()`:

```python
from verisim.integrations.sqlalchemy import verisim_factory

user_factory = verisim_factory(User, seed=123)
user = user_factory.build()

session.add(user)
session.commit()
```

Django factories support unsaved builds and manager-backed creates:

```python
from verisim.integrations.django import verisim_factory

user_factory = verisim_factory(User, seed=123)
unsaved_user = user_factory.build()
saved_user = user_factory.create()
```

Pytest helpers wrap `@pytest.fixture` with deterministic seeded records and
normal fixture scopes:

```python
from verisim.integrations.pytest import verisim_fixture

user = verisim_fixture(User, adapter="sqlalchemy", scope="function", seed=123)
```

The integrations map common field names such as `email`, `username`,
`first_name`, `city`, `domain`, and `company_name` from coherent Verisim facts,
then fall back to framework field types and simple constraints such as choices,
lengths, nullability, defaults, and required parent relationships.

Implementation: [SQLAlchemy factories](sqlalchemy.py),
[Django factories](django.py), [pytest fixtures](pytest.py), and
[shared value generation](_core.py).
