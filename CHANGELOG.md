# Changelog

All notable changes to **semRTI** are documented here.

This project follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`), implemented
as Git tags. Each release entry below must be reflected in `component.md` (`release-number`,
`release-date`, `release-link`, `doi`) and, once archived, `CITATION.cff`.

Structure each release as:

```
## [X.Y.Z] - YYYY-MM-DD

One-sentence summary of the release.

### Added
### Changed
### Fixed
### Deprecated
### Removed
```

Reference issues, pull requests, or commits (e.g. `#12`) to help trace the reason for a change.

## [Unreleased]

### Added

- INFINITY Ecosystem governance/metadata scaffold (`component.md`, `codemeta.json`,
  `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`,
  `MAINTAINERS.md`, `docs/governance.md`, `docs/release-process.md`, `docs/ethics/`), adopted from
  [`infinity-project/infinity-template`](https://codeberg.org/infinity-project/infinity-template).

## [1.0.1] - 2026-06-26

The RelightLab plugin no longer emits RDF. It now writes an ontology-neutral provenance JSON, and
all ontology logic lives in a Python KG Builder. See
[Version.1.0.1-Report.md](Version.1.0.1-Report.md) for the full migration report and
[RupeMagnaOnto-Plan2-Report.md](RupeMagnaOnto-Plan2-Report.md) for the accompanying data-correction
plan.

### Changed

- RDF plugin (`01-pipeline/rdf-plugin`) rewritten to export ontology-neutral JSON
  (`info.json` + `F0xRTIxx-ptm.json`) instead of RDF/TTL, separating the technical record (C++)
  from ontology mapping (Python).
- Project metadata consolidated into a single source of truth, `enrich-metadata.json`.
- Knowledge graph assembled in memory into one final `.ttl`, replacing concatenated,
  multi-header intermediate files.
- Data-correction pass (T1–T12, V1–V6) applied to the produced graph — see
  RupeMagnaOnto-Plan2-Report.md.

## [1.0.0] - 2026-06-26

Initial tagged release of the semRTI pipeline (RelightLab RDF plugin + Python KG Builder),
converting Rupe Magna RTI survey data into a CHS-ODP/ArCo-aligned RDF/Turtle knowledge graph.
