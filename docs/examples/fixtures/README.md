# Application configuration template

`fixtures.yaml` is a supported configuration template for a Django/Pydantic
application with a caller-owned knowledge graph adapter and API runner.
`branches.json` illustrates the normalized catalog the adapter must return.
The shop modules and code locations are placeholders; replace them with your
application before invoking this configuration.

For an immediately runnable project, use the
[API fixture example](../../../examples/api_fixtures/README.md).
For callback interfaces, constraints, receipt requirements and exit codes, read
the [fixture API guide](../../fixtures/README.md).

`project.root` is relative to the config file; other paths are relative to the
project root. Set `SOURCE_REVISION` and `KNOWLEDGE_GRAPH_URL` before loading this
template. `token_env` tells your adapter which environment variable to read;
the library does not fetch graph credentials itself.

For a normalized file catalog, replace the branch adapter with
`verisim.fixtures.adapters.file:load_branches` and set its only option to
`path: contracts/branches.json`. The file's revision and complete operation scope
must match the configuration.
