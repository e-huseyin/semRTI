# Tests

Per the Technical Rulebook, plan testing from the moment a component is designed, before coding
starts — ideally with a test case per function/method as it is implemented.

## Requirements

- **Unit tests** for every function/usage case; **integration tests** where applicable.
- Recommended minimum coverage: **≥ 80%** (e.g. via `coverage.py` for Python). Consider adding a
  coverage badge to the README.
- Tests must be **lightweight, self-contained, and easy to run** by anyone, with clear
  instructions to configure and run them and a clear statement of the expected result of each
  test.
- Prefer **mocked-up data** as test inputs.
- CI must run these tests automatically on push/PR (see `.forgejo/workflows/ci.yml`) so broken
  code is caught before merge.

## Layout

Keep test code in this directory (or language-conventional subfolders, e.g. `tests/unit/`,
`tests/integration/`), mirroring the structure of the pipeline (`01-pipeline/` for the KG Builder
and RDF plugin).

## Ontology / knowledge graph components

semRTI produces a knowledge graph aligned to CHS-ODP and ArCo. Include a separate folder of
ontology tests following the eXtreme Design methodology (the
[XDTesting](https://github.com/extreme-design/xd-testing) tool is recommended) — e.g. competency
question SPARQL queries run against `03-outputs/` graphs, and SHACL shape validation.
