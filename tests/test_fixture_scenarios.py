from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from verisim.fixtures.scenarios import generate_candidates


class CreateItem(BaseModel):
    name: str
    count: int = 1


def test_builds_deterministic_positive_and_branch_specific_scenarios():
    config = SimpleNamespace(
        project=SimpleNamespace(revision="rev-1"),
        operations={
            "create": SimpleNamespace(
                request_model="request", fixture_models=[], fixture_rows={}, bindings={}
            )
        },
        generation=SimpleNamespace(
            seed=17, clock="2026-01-01T00:00:00Z", candidate_limit=20, candidates=[]
        ),
    )
    sources = SimpleNamespace(
        operations={
            "create": SimpleNamespace(
                method="POST",
                path="/items",
                parameters=(),
                request_schema=CreateItem.model_json_schema(),
                request_content_type="application/json",
                request_required=True,
            )
        },
        model_classes={"request": CreateItem},
        model_schemas={"request": CreateItem.model_json_schema()},
        input_fingerprint="sha256:inputs",
    )
    catalog = SimpleNamespace(
        targets=(
            SimpleNamespace(
                id="yes",
                operation_id="create",
                constraints=({"path": "request.body.count", "op": "gte", "value": 2},),
            ),
            SimpleNamespace(
                id="no",
                operation_id="create",
                constraints=({"path": "request.body.count", "op": "lt", "value": 2},),
            ),
        )
    )

    pool = generate_candidates(config, sources, catalog)
    assert len(pool.scenarios) == 2
    counts = {scenario.request["body"]["count"] for scenario in pool.scenarios}
    assert counts == {1, 2}
    assert len({scenario.id for scenario in pool.scenarios}) == 2
    assert pool.scenarios == generate_candidates(config, sources, catalog).scenarios


def test_explicit_seed_and_candidate_cap_are_respected():
    config = SimpleNamespace(
        project=SimpleNamespace(revision="rev-1"),
        operations={
            "create": SimpleNamespace(
                request_model=None, fixture_models=[], fixture_rows={}, bindings={}
            )
        },
        generation=SimpleNamespace(
            seed=1,
            clock="2026-01-01T00:00:00Z",
            candidate_limit=1,
            candidates=[
                SimpleNamespace(
                    operation_id="create",
                    values={"request.body.name": "seed"},
                    expectations={},
                )
            ],
        ),
    )
    sources = SimpleNamespace(
        operations={
            "create": SimpleNamespace(
                method="GET",
                path="/items",
                parameters=(),
                request_schema=None,
                request_content_type=None,
                request_required=False,
            )
        },
        model_classes={},
        model_schemas={},
        input_fingerprint="fp",
    )
    catalog = SimpleNamespace(
        targets=(
            SimpleNamespace(id="a", operation_id="create", constraints=()),
            SimpleNamespace(id="b", operation_id="create", constraints=()),
        )
    )
    pool = generate_candidates(config, sources, catalog)
    assert len(pool.scenarios) == 1
    assert pool.scenarios[0].request["body"]["name"] == "seed"
    assert pool.limit_reached is True


def test_django_rows_preserve_relations_and_validate_scalar_fields():
    class Field:
        def __init__(self, name, *, relation=None):
            self.name = name
            self.many_to_one = relation is not None
            self.one_to_one = False
            self.remote_field = SimpleNamespace(model=relation) if relation else None
            self.null = False

        def clean(self, value, instance):
            if value is None:
                raise ValueError("required")
            return value

    class Organization:
        _meta = SimpleNamespace(concrete_fields=[Field("name")])

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class User:
        _meta = SimpleNamespace(
            concrete_fields=[
                Field("email"),
                Field("organization", relation=Organization),
            ]
        )

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    config = SimpleNamespace(
        project=SimpleNamespace(revision="rev-1"),
        operations={
            "create": SimpleNamespace(
                request_model=None,
                fixture_models=["organization", "user"],
                fixture_rows={"org": "organization", "person": "user"},
                bindings={},
            )
        },
        generation=SimpleNamespace(
            seed=1, clock="2026-01-01T00:00:00Z", candidate_limit=10, candidates=[]
        ),
    )
    sources = SimpleNamespace(
        operations={
            "create": SimpleNamespace(
                method="POST", path="/users", parameters=(), request_schema=None
            )
        },
        model_classes={"organization": Organization, "user": User},
        model_schemas={
            "organization": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
            "user": {
                "type": "object",
                "required": ["email"],
                "properties": {"email": {"type": "string"}},
            },
        },
    )
    catalog = SimpleNamespace(
        targets=(SimpleNamespace(id="created", operation_id="create", constraints=()),)
    )
    scenario = generate_candidates(config, sources, catalog).scenarios[0]
    rows = {row["ref"]: row for row in scenario.fixture_rows}
    assert rows["person"]["relations"]["organization"] == {"$ref": "org"}
