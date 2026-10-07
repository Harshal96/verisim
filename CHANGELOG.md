# Changelog

## 0.2.0

- Generate replayable API fixture scenarios from Swagger/OpenAPI contracts and
  Django/Pydantic models through the `verisim fixtures` CLI and Python API.
- Accept caller-owned branch catalogs and runners; select the fewest scenarios
  within the measured candidate pool using exact set cover and verify replay.
- Export lossless JSON, CSV and SQLite bundles with typed values, execution
  receipts, revision-pinned provenance and atomic publication.
- Support logical predicates, absent rows, actor/environment state, deterministic
  generation, relationship refs and request-to-fixture bindings.
- Include a runnable Django example with real Coverage.py branch measurements,
  user guides and configuration templates.
- Package the domain models, structured exports, integrations, statistical
  controls, masking, activity streams, synthetic AI training data and developer
  helpers added since the initial release.

## 0.1.0

- Initial release of coherent synthetic domain data generation with Pydantic
  models, deterministic seeds, locale data and a command-line interface.
