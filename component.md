---
component-id: "semrti"
type: "Workflow"
name: "semRTI"
description: "A self-contained, menu-driven pipeline that converts Reflectance Transformation Imaging (RTI) survey data into a FAIR-compliant RDF/Turtle Knowledge Graph, aligned to the Cultural Heritage Survey Ontology Design Pattern (CHS-ODP) and ArCo."

# Mandatory: at least one licence code from REECO's controlled vocabulary
# (reeco-python/src/reeco/schema/licences.yml). This is NOT SPDX -- see the
# licence note below. This repository's actual LICENSE is CC BY 4.0; "CC-BY-4.0"
# is used here as the REECO code on the same assumption the template applies to
# MIT/Apache-2.0 (that it happens to match SPDX) -- NOT independently confirmed
# against the REECO vocabulary. Verify with the validator command below before
# release and correct if REECO uses a different code (e.g. `CC_BY_4.0`) or has
# none at all.
licence:
- "CC-BY-4.0"

# Mandatory: must be present, even as an empty list. Each item is a dict
# using one or more of: informed-by, use-case, story, persona, documentation,
# derived-from, evaluated-in, extends, reuses, serves, produces, reused-in,
# generated-by. Remove the [] and add entries once relations exist, e.g.:
#   related-components:
#   - extends:
#     - another-component
#   - reuses:
#     - another-component
#     - another-dataset
related-components: []

work-package:
- "WP8"
pilot:
- "3DARCHEO"
project: infinity-project
release-date: "2026-06-26"
release-number: "1.0.1"
changelog: "https://codeberg.org/erdoganhuseyin/semRTI/src/branch/main/CHANGELOG.md"
contributors:
- "Hüseyin Erdoğan <Alma Mater Studiorum – Università di Bologna, huseyin.erdogan@unibo.it>"

# Optional and validated LIVE over HTTP by reeco.Validator when present (it
# issues an HTTP HEAD request against the URL at validation time). Leave
# commented out until the URL actually resolves -- a placeholder value here
# fails validation, whereas an absent key is simply skipped. Keep the quotes
# when you uncomment these: a bare `{{...}}` at the start of a YAML scalar is
# parsed as flow-mapping syntax and breaks the file (see notes below).
# image: "{{IMAGE_URL}}"
# logo: "{{LOGO_URL}}"
# demo: "{{DEMO_URL}}"
# release-link: "{{RELEASE_LINK}}"
# doi: "{{DOI}}"

# ============================================================================
# INFINITY Rulebook extensions
# ----------------------------------------------------------------------------
# Not part of the REECO schema -- ignored by reeco.Validator (it validates
# with ignore_extra_keys=True), so harmless to include, but also not lifted
# into the ecosystem's RDF/knowledge graph output. Kept here because the
# rulebook's own YAML header example includes them.
# ============================================================================
copyright: "Copyright (c) 2026 The Infinity Project Contributors"
credits: "This project has received funding from the European Union's Horizon Europe research and innovation programme under grant agreement N. 101233051"
---

# semRTI

This file exposes the INFINITY Ecosystem annotations for this component. It is consumed as-is by
the INFINITY Ecosystem website (built on REECO/Jekyll), so keep the YAML header both REECO-valid
and up to date at every release.

## Notes for editing this file

- **`type`** must be one of REECO's component subtypes, computed from the type hierarchy in
  `reeco-python/src/reeco/schema/schema.yml` (walked recursively from `Component`) -- not just the
  rulebook's illustrative "main categories" list. The main categories (`Data`, `Application`,
  `Software`, `Report`, `Dataset`, `Ontology`, `KnowledgeGraph`) are valid, but so are their more
  specific subtypes: `Repository`, `Registry`, `Corpus`, `Lexicon`, `KnowledgeGraph`, `WebSite`,
  `WebApplication`, `WebService`, `SPARQLEndpoint`, `MobileApp`, `CLITool`, `Workflow`, `API`,
  `UserInterface`, `DockerImageContainer`, `SoftwareLibrary`, `Notebook`, `Script`,
  `RequirementsCollection`, `Story`, `Persona`, `Mockup`, `Survey`, `InPresenceSurvey`,
  `FocusGroup`, `Documentation`, `Tutorial`, `EvaluationReport`. Avoid `EcosystemWebsite` and
  `Deliverable`: both are documented but currently unreachable due to a `supertype-id` mismatch
  bug in upstream `schema.yml` (case/whitespace), so they fail validation despite looking valid.
  `Workflow` was chosen here because semRTI is a multi-stage pipeline (plugin → JSON → KG Builder →
  `.ttl`) rather than a single script or library; reconsider if `CLITool` or `Software` fits better
  once the ecosystem site's rendering of this component is reviewed.
- **`licence`** must be a list of codes from REECO's own vocabulary
  (`reeco-python/src/reeco/schema/licences.yml`, ~340 entries derived from DALICC), **not SPDX
  identifiers**. `MIT` and `Apache-2.0` happen to match SPDX; most others don't (e.g. GPLv3 is
  `GNU_GPL_v3`, not `GPL-3.0`). This repository's `LICENSE` is CC BY 4.0; `CC-BY-4.0` is used above
  on the unverified assumption it also matches SPDX in REECO's vocabulary the way MIT/Apache-2.0
  do -- confirm with the validator command below and correct if not.
- **`related-components`** must be present (an empty list is valid) -- REECO treats a missing key
  as an error, not a missing-but-optional field.
- Validate locally before pushing: `pip install reeco && python -c "import frontmatter, reeco, sys; a,_ = frontmatter.parse(open('component.md').read()); v = reeco.Validator(); r = (v.asComponent(a) if 'component-id' in a else v.asContainer(a)); print(r)"`
- A repository may contain multiple annotated component files (any filename); duplicate this
  structure per component if so.
- Component types: https://github.com/reeco-framework/reeco-annotation-schema/blob/main/schema/README.md
