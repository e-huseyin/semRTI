# Release process

This describes how a component in this repository moves from ready-for-release to an official,
citable part of the INFINITY Ecosystem, per the Technical Rulebook.

## 1. Champion plans the release

- The Champion decides release frequency and rationale for this component.
- Internal agreement that the release is ready is recorded in the repository (an Issue/PR).

## 2. Technical Board (TB) is informed

- The Champion notifies the TB of the planned release, proposed version number, and expected
  deadline.
- The Champion ensures `component.md` metadata is accurate before submission.

## 3. Technical review

Before a release is approved, a technical review is carried out by the TB (divided by component
expertise; reviewers cannot include contributors to this component or members of the Champion's
organisation). The review covers:

- code tests performed and passed,
- a security check,
- rulebook compliance (documentation present, ethics declaration completed — see
  [docs/ethics/](ethics/)).

Testing/validation is normally scheduled at a TB meeting and completed by the next one, unless
project-specific urgency requires otherwise.

## 4. Champion makes the release

On TB approval, the component version becomes an official part of the INFINITY Ecosystem.

1. Tag the release in Git using **Semantic Versioning**: `MAJOR.MINOR.PATCH`
   (breaking / backward-compatible feature / bug fix).
2. Write release notes in [CHANGELOG.md](../CHANGELOG.md):

   ```
   ## Version X.Y.Z - YYYY-MM-DD

   One-sentence summary.

   ### Added
   ### Changed
   ### Fixed
   ### Deprecated
   ### Removed
   ```

   Reference issues, PRs, or commits for traceability.
3. Create a release in Codeberg from the tag.

## 5. Archive on Zenodo

There is no automatic sync between Codeberg and Zenodo — do this manually:

1. Download the release archive from Codeberg (`.zip` or `.tar.gz`).
2. Upload it as a new (or new version of an existing) software record on Zenodo.
3. Complete the Zenodo metadata fields.
4. Copy the minted DOI into:
   - `component.md` (`doi`, `release-link`),
   - `README.md` (as a badge or citation section),
   - `CITATION.cff` (`doi`, `date-released`, `version`),
   - `codemeta.json` (`identifier`, `version`, `datePublished`).

## 6. Update the Ecosystem website

The INFINITY Ecosystem website reads `component.md` directly from Codeberg — no separate
publishing step is needed once the file is updated and pushed, but double-check the rendered page
after release.

## Ethics declaration

Every release must be accompanied by an up-to-date **Digital Heritage Ethics Declaration**
submitted to the Technical Board — see [docs/ethics/digital-heritage-ethics-declaration.md](ethics/digital-heritage-ethics-declaration.md).
