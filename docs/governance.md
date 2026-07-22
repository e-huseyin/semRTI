# Governance

This document summarises the governance model from the Technical Rulebook for INFINITY
Developers as it applies to this repository.

## The Champion

Every repository must always have an active Champion: a person from the INFINITY project
consortium, normally working for the partner leading the work package/task under which this
component is developed. The Champion is the **technical owner and accountability point** for the
repository. The current Champion (and optional deputy) is recorded in
[MAINTAINERS.md](../MAINTAINERS.md).

The Champion's responsibilities:

1. **Technical leadership** — architecture/design, technical standards, approving major changes,
   ecosystem compatibility, long-term technical vision.
2. **Repository stewardship** — structure and documentation, required files present and updated,
   issue tracking, consistent code organisation, dependency hygiene.
3. **Code review and QA** — reviewing (or delegating review of) pull requests, enforcing style and
   test coverage, ensuring CI passes before merge, rejecting substandard contributions.
4. **Contributor coordination** — onboarding, assigning work, mentorship, resolving disagreements.
5. **Security oversight** — triaging vulnerability reports, coordinating fixes, secure dependency
   management, vulnerability disclosure process.
6. **Release management** — approving release candidates, enforcing semantic versioning,
   maintaining the changelog, tagging releases.
7. **Ecosystem alignment** — following ecosystem technical policies, coordinating with related
   components, participating in governance discussions.
8. **Documentation ownership** — accurate README, current technical docs, API docs, onboarding
   docs.
9. **Maintenance and sustainability** — monitoring activity, preventing stagnation, recruiting
   maintainers, planning the roadmap, initiating deprecation if the project becomes obsolete.
10. **Accountability** — responding to governance inquiries, timely handling of technical/security
    issues, rulebook compliance, and stepping down or nominating a successor if they can no longer
    maintain the project.

A deputy may be named to stand in for the Champion when they are unavailable.

## Contributors

See [CONTRIBUTING.md](../CONTRIBUTING.md) for who may contribute and under what terms (CLA, Code
of Conduct, rulebook compliance).

## Discussion and decision-making

- Discussions must be recorded in this repository's Issues, even if they started elsewhere.
- Proposals must clearly state who is proposing what.
- Sufficient time must be given for discussion before a decision is made.
- Decisions may be put to a vote of registered contributors, but the Champion has the final word.
- Agreed changes must name a responsible person and, ideally, a delivery deadline.

## Naming conventions

**Repositories:**

- Avoid including "INFINITY" in the name (e.g. `ecosystem`, not `infinity-ecosystem`).
- Avoid acronyms and vague/ambiguous words; use commonly understood abbreviations only.
- Consider including the component type in the name when the same functionality ships in
  different forms (e.g. `sdk-textminer` vs `api-textminer`).
- Use a primary/secondary name to group variants or companion components (e.g. `x-python`,
  `x-rust`).
- Lowercase only, hyphens not underscores, no version numbers in the name.

**Ontologies:** `[name-of-ontology]-ontology` (e.g. `mkg-ontology`).

**Knowledge graphs:** `[name-of-kg]-kg` (e.g. `politics-kg`).

## Branching

Use branches to manage different versions of the same component. Do not create a branch per
sub-system (e.g. `/datasets`, `/ui`) — split those into separate, well-named repositories instead.

## Ecosystem components and containers

- An **Ecosystem component** is any resource produced by or used in the research activity.
- An **Ecosystem container** groups components representing a research activity (e.g. a project).
- This repository exposes at least one component via an annotated markdown file (see
  [component.md](../component.md)); a repository may expose multiple components via multiple
  annotated files.
