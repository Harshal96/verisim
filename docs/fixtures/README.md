# API branch fixtures

Verisim generates a finite pool of replayable API scenarios, asks your runner
which branches each scenario actually reaches, and selects the fewest scenarios
that cover your declared catalog. It replays the selection before publishing a
bundle. The minimum is proven within that measured pool, not across every
possible program input.

Start with the [runnable Django/Pydantic example](../../examples/api_fixtures/README.md).
The [configuration template](../examples/fixtures/fixtures.yaml) shows where to
connect your own application and knowledge graph.

## Invocation

```bash
uv add 'verisim[fixtures,django]'
verisim fixtures --config fixtures.yaml
verisim fixtures --config fixtures.yaml --format csv --output out/scenarios.csv
verisim fixtures --config fixtures.yaml --format sqlite --output out/scenarios.sqlite
```

JSON configurations work without the `fixtures` extra; YAML requires PyYAML.
FastAPI request models use the Pydantic source. The caller can use an ASGI test
client without running a network server.

```python
from verisim.fixtures import generate_fixtures, load_config
from verisim.fixtures.exporters import read_bundle

result = generate_fixtures(load_config("fixtures.yaml"))
if result.fixture_path:
    bundle = read_bundle(result.fixture_path, "json")
    for scenario in bundle["scenarios"]:
        print(scenario["id"], scenario["request"], scenario["fixture_rows"])
```

`project.root` is relative to the configuration file. Python paths, OpenAPI
files, and output paths are relative to that root. Paths in results are absolute.
Model and callback references use `module:attribute`; imports remain available
throughout execution, including callbacks and their lazy imports. Unknown core
configuration keys are rejected. `${NAME}` expands explicit environment
variables and fails when a referenced variable is absent.

## Branch catalog adapter

The generic interface is a Python callback. Your adapter can query an internal
graph endpoint, translate its native data, and return this normalized contract:

```python
def load_branches(*, options: dict, context: dict) -> dict:
    # Fetch/translate your graph here, using the pinned revision and operations.
    return {
        "version": 1,
        "source_revision": context["source_revision"],
        "scope": {"complete": True, "operations": ["createOrder"]},
        "targets": [
            {
                "id": "customer.active.true",
                "operation_id": "createOrder",
                "arc": {"file": "shop/api.py", "from_line": 42, "to_line": 43},
                "constraints": [
                    {"path": "fixtures.customer.is_active", "op": "eq", "value": True}
                ],
            }
        ],
    }
```

Context contains `project_root`, `source_revision`, `selected_operations`,
`input_fingerprint`, and `source_files`. Declare the complete selected operation
scope. Target IDs must be unique, and each target belongs to one selected
operation. Arcs are optional when your collector uses its own stable branch IDs.
An adapter is responsible for truthful catalog completeness and revision pinning.

For a pre-exported normalized JSON catalog:

```yaml
branches:
  adapter: verisim.fixtures.adapters.file:load_branches
  options:
    path: contracts/branches.json
```

For an internal endpoint, point `adapter` at your module and pass its URL and
token environment-variable name through `options`. The library does not assume
a graph vendor, HTTP authentication scheme, or query language. Store credential
references, rather than live credentials, in configuration: configuration and
callback options are retained as provenance in the exported bundle.

## Candidate construction

Each scenario contains one measured request, Django `fixture_rows`, logical
`actor` and `environment` mappings, expectations, a seed, and a pinned clock.
Rows use named refs; foreign keys are explicit `{"$ref": "parent"}` relations.
Your runner creates rows and resolves relations before measurement.

Supported predicates are `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in`,
and `exists`, composed with `all`, `any`, and `not`. Paths begin with `request`,
`fixtures`, `actor`, or `environment`. Requests expose `body`, `query`,
`path_parameters`, and `headers`; numeric components address array indexes.
`fixtures.customer` addresses a named row, so `exists: false` removes that row.

Construction searches a bounded domain of values suggested by the predicates.
It verifies the complete predicate expression after construction. An exhausted
search, unsupported construction, invalid persisted row, or binding conflict
is recorded under `generation_diagnostics`; it is never proof of unreachability.
Provide explicit seeds for application-specific values or difficult predicates:

```yaml
generation:
  seed: 42
  clock: '2026-10-07T00:00:00Z'
  candidate_limit: 500
  candidates:
    - operation_id: createOrder
      values:
        actor.admin: true
        environment.inventory_online: true
        request.body.quantity: 2
        fixtures.customer.email: buyer@example.invalid
      expectations:
        status: 201
```

Candidate identities include canonical scenario content, seed, and clock, and
exclude receipts and discovery order. Identical candidates share an identity.
The cap limits unique candidates submitted to the runner. Different expectations
are different replay contracts and therefore produce different identities.

Django sources load every configured model and generate distinct primary keys
for multiple rows. Scalar field validation converts dates, UUIDs and decimals
to their runtime types. Constant defaults are retained; date/time and UUID
generation is deterministic. Arbitrary callable defaults require an explicit
deterministic adapter. Field uniqueness is checked within each scenario; your
runner must enforce database constraints during persistence. Ambiguous foreign
keys require an explicit relation ref in candidate values. Missing required
rows/fields and dangling references reject a candidate.

Bindings map a destination path to a source path:

```yaml
operations:
  createOrder:
    request_model: create_order
    fixture_models: [customer]
    fixture_rows:
      buyer: customer
      seller: customer
    bindings:
      request.body.customer_id: fixtures.buyer.id
```

A missing binding source or a conflict with an explicit destination value is
reported. When a constraint deliberately removes the source row, the request
retains its generated destination ID to exercise the missing-row branch.
Invalid request values may intentionally reach API validation branches;
invalid persisted Django rows are rejected before execution.

Swagger 2 and OpenAPI 3.0/3.1 request schemas, internal schema references,
Pydantic nested models, and nullable `anyOf` schemas are supported. Unsupported
schema keywords are rejected explicitly. This is a constrained generator,
not a complete JSON Schema solver.
Configured Pydantic payloads are intersected with the OpenAPI request contract;
conflicting field types or bounds fail source loading, and incompatible defaults
are discarded when constructing positive inputs.

## Runner and required receipts

```python
def run_scenario(scenario: dict, *, context: dict) -> dict:
    # Establish a clean baseline, create rows, resolve credentials/dependencies.
    # Measure exactly one API invocation; exclude setup and cleanup coverage.
    # Always clean up, including application failures.
    return {
        "version": 1,
        "scenario_id": scenario["id"],
        "operation_id": scenario["operation_id"],
        "source_revision": context["source_revision"],
        "input_fingerprint": context["input_fingerprint"],
        "execution_valid": True,
        "coverage_valid": True,
        "isolated": True,
        "measured_invocations": 1,
        "observed_branch_ids": ["customer.active.true"],
        "checks_passed": True,
        "diagnostics": [],
    }
```

Every field shown above is required. Context includes `effective_clock`,
`catalog_targets` with arcs, `target_ids_by_operation`, revision, fingerprint,
and `options` from `execution.options`. Your runner applies the clock to the
application under test and resolves the declared actor/environment state.
Callbacks run sequentially. Callback stdout is redirected to stderr so CLI
stdout remains machine-readable.

Only attributed, structurally valid, isolated receipts contribute coverage.
Branch IDs outside the scenario's selected operation invalidate its receipt.
Expected errors can pass checks. An unexpected response can fail checks while
still yielding trustworthy coverage. Runner exceptions invalidate measurement.
Coverage and application assertions are kept separate.

The exact solver selects the minimum scenario count within coverage-valid
measurements. A timeout leaves optimality unproven. The selected scenarios run
again from clean baselines; their observed sets must match the originals and
cover all required targets. Isolation and instrumentation depend on your runner's
truthful receipt; the core cannot independently inspect a remote runner's state.

## Output and process contract

JSON, CSV, and SQLite reconstruct the same logical bundle with `read_bundle`.
CSV embeds nested JSON in cells. SQLite stores a portable scenario bundle,
not a populated application database. A bundle is also distinct from Django
`loaddata` JSON.

Dates, datetimes, UUIDs, and decimals use versioned `$verisim` JSON tags. The
reader restores their types, including decimal precision. Literal dictionaries
containing the reserved tag are escaped to prevent accidental type conversion.

Bundles and JSON reports retain configuration/catalog snapshots and fingerprints,
source hashes, callback references/options/source hashes, identifiable package
versions, library and data-pack fingerprints, effective clock, and replay adapter
requirements. They contain the original and replay receipts. Changes to pinned
inputs during generation reject publication.

CLI stdout contains one JSON manifest. Logs go to stderr. The manifest reports
independent `coverage_complete`, `optimal_within_pool`, `replay_verified`, and
`checks_passed` flags, absolute artifact paths, run ID, scenario count, and the
SHA-256 of the actual fixture file bytes.

| Exit | Meaning |
| --- | --- |
| 0 | Full coverage, proven pool optimum, stable replay, passing checks. |
| 2 | Configuration, source, catalog, or callback-contract error. |
| 3 | Coverage incomplete, optimum unproven, or replay invalid. |
| 4 | A verified bundle was published, but selected application checks failed. |
| 5 | Fixture or report publication failed. |

Publication uses temporary sibling files, validates serialization, and publishes
the report before the fixture. Failures preserve an older fixture and return
`fixture_path: null`. Consumers should compare manifest/report run IDs and the
fixture digest before accepting an artifact pair. Output paths cannot overwrite
configuration, OpenAPI, imported model/callback, or file-catalog inputs.
