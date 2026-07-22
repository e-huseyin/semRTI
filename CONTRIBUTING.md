# Contributing to semRTI

Thank you for your interest in contributing. This repository is part of the INFINITY Ecosystem
and follows the [Technical Rulebook for INFINITY Developers](docs/) v1.0. Please read this file
before opening an issue or pull request.

## Who can contribute

Contributors are usually developers working for organisations that are INFINITY project
consortium members and named contributors to the work package/task under which this component
is developed. Anyone else may contribute provided they:

- are permitted to do so by the Champion of this repository (see [MAINTAINERS.md](MAINTAINERS.md)),
- accept the Contributor Licence Agreement below,
- follow the [Code of Conduct](CODE_OF_CONDUCT.md),
- comply with the Technical Rulebook.

Contributors must use a verified developer identity to ensure accountability. The Champion has
final discretion over external contributions and is accountable for them on behalf of the
INFINITY project.

## Contributor Licence Agreement (CLA)

By submitting a contribution to this repository, you agree to the following:

> All contributors grant the project a perpetual, worldwide, non-exclusive, royalty-free licence
> to use, reproduce, modify, and distribute their contributions as part of this component.

## Git workflow

We follow [GitHub Flow](https://githubflow.github.io/): the `main`/`master` branch is always
deployable, feature work happens on short-lived branches, and changes land via pull request.

- Use branches to manage different versions of the code, not different sub-systems. If a
  sub-system deserves independent versioning, it belongs in its own repository (see naming
  conventions in [docs/governance.md](docs/governance.md)).
- Keep pull requests focused and reviewable.
- Ensure CI passes before requesting a merge.

## Commit messages

- Commit messages are **mandatory** and must reference at least one Issue.
- Commits SHOULD follow [Conventional Commits](https://github.com/angular/angular/blob/22b96b9/CONTRIBUTING.md#-commit-message-guidelines)
  (`type(scope): description`) to enable automated changelog generation, semantic versioning, and
  AI-assisted analysis.

## Discussion and decisions

- All discussion relevant to this component's development must be recorded in this repository's
  Issues, even if it started elsewhere (a work package meeting, chat, etc.). **If it isn't
  recorded here, it never happened.**
- Actions that would impact the component's development must be logged as an Issue, motivated by
  whoever calls for the action, with enough time for participants to discuss before a decision is
  taken.
- Decisions may be based on a vote of registered contributors to this repository, but the
  Champion always has the last word.
- An agreed implementation change must name a responsible person and, ideally, a delivery
  deadline; implementation can continue in the same issue where the decision was made.

## Progress reporting

Issue #1 in this repository is reserved for periodic progress updates (at least monthly, aligned
with work package meetings), using the **3P** format:

- **Progress** — concrete work done since the last update.
- **Problems** — anything slowing or blocking progress.
- **Perspectives** — expected progress going forward, including plans to address problems.

Detailed, task-specific issues should be opened separately and linked from the progress issue
when relevant.

## Code quality expectations

- Follow the style guide adopted for this component's language (e.g. PEP8 for the Python KG
  Builder, standard C++ conventions for the RelightLab plugin).
- Include unit tests (and integration tests where applicable). Aim for ≥ 80% coverage.
- Ensure CI (tests, lint, security scan, dependency check) passes before merging.
- Document functions/classes and source files as described in the rulebook's code documentation
  guidelines.

## Before opening a pull request

Run:

```bash
./scripts/validate.sh
```

This checks the repository against the mandatory Rulebook requirements (files present, YAML
metadata valid, tests present, etc.).
