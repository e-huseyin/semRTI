# AI Usage Policy

This document describes, in clear terms, what AI systems are and are not allowed to do with the
contents of this repository, and how AI assistance was used in creating it. It complements the
machine-readable [`ai.txt`](ai.txt) file (dual-layer policy: this file for humans and AI system
developers, `ai.txt` for automated agents).

## AI assistance used in this repository

> Claude Code (Anthropic) was used to scaffold this repository's INFINITY Ecosystem governance and
> metadata files (`component.md`, `codemeta.json`, `CITATION.cff`, `CONTRIBUTING.md`,
> `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, `MAINTAINERS.md`, `docs/`) from
> `infinity-project/infinity-template`, and for drafting/formatting parts of `README.md`.

All AI-generated contributions — code and documentation alike — have been reviewed by the Champion
before merging, per the Technical Rulebook. This section should be updated by the Champion to
describe any AI assistance used in the pipeline code itself (`01-pipeline/`), if applicable.

## What AI systems may do with this repository

- **Training**: Permitted, provided the licence terms in [LICENSE](LICENSE) (CC BY 4.0) are
  respected, in particular attribution.
- **Indexing / retrieval**: Permitted for search and discovery purposes.
- **Reuse in generated code or content**: Permitted, provided attribution requirements below are
  met — consistent with CC BY 4.0.
- **Attribution requirements**: any reuse must retain the copyright notice and licence terms in
  [LICENSE](LICENSE), and cite this repository as described in [CITATION.cff](CITATION.cff).

## Restrictions

- AI agents must not represent generated output as an official INFINITY Ecosystem release without
  human review and Technical Board approval (see [docs/release-process.md](docs/release-process.md)).
- AI agents must not bypass or alter any ethics or licensing declarations in this repository
  (see [docs/ethics/](docs/ethics/)).

## Machine-readable policy

See [`ai.txt`](ai.txt) for the machine-readable equivalent of the rules above, aligned with the
[proposed `ai.txt` convention](https://arxiv.org/html/2505.07834v1) (analogous to `robots.txt`).
