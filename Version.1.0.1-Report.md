# Index

- [[#0. Overview]]
- [[#1. The problem (why it was changed)]]
- [[#2. The decision (separation of concerns)]]
- [[#3. The new architecture]]
- [[#4. The concrete changes (file by file)]]
- [[#5. The data-correction layer (summary + link)]]
- [[#6. Current status & remaining work]]

---

# semRTI — Pipeline Migration Report — Version 1.0.1

*Reflectance Transformation Imaging (RTI) → Knowledge Graph pipeline for cultural heritage (Rupe Magna).*

## 0. Overview

**What this report covers.** This document describes, from start to finish, the **migration from the old pipeline to the new one** (the architectural redesign): the problem identified, the decisions taken, the resulting new architecture, and the concrete file-level changes.

**There are two distinct changes — they must not be conflated:**

- **(A) Pipeline redesign** *(20–23 June 2026)* — a change to the architecture itself: the RDF plugin now emits **ontology-neutral JSON** instead of RDF/TTL; a separation of concerns (C++ plugin = technical record / Python KG Builder = ontology); a single-source `enrich-metadata.json`; and a Python KG Builder that writes one final `.ttl`. **This report is about (A).**

- **(B) Data correction** *(25 June 2026)* — accuracy and hygiene fixes to the *graph the new pipeline produces* (T1–T12, V1–V6). **This is documented separately in [[RupeMagnaOnto-Plan2-Report]].** This report does not repeat it; it only summarises it and points to that document.

**Basis of verification.** Every technical claim in this report was checked by comparing the two versions in the actual code: the pre-change first version **`sem-RTI-version.1.0`** and the current new version **`semRTI`**. Each item is labelled:

- **✅ verified** — confirmed directly from the code/files;

- **⚠️ author's record, consistent with observation** — based on the author's notes; consistent with the measured magnitudes, but the exact state at that moment cannot be reproduced now.

**Out of scope.** The design of the ontology itself (`rupemagna-rti-ontology.owl`) and the SHACL shapes are not the subject of this report; only how the pipeline uses them is described.

## 1. The problem (why it was changed)

In the old architecture, the RelightLab **RDF plugin** was originally meant only to export the **technical information** produced during RTI processing into RDF. Over time, however, **ontological decisions** had crept into the plugin's C++ code as well:

- creator, organisation, website
- coordinates, licence
- cultural-heritage entities, survey metadata, figure metadata
- CHS-ODP class/property mappings
- provenance modelling
- and the plugin **read the JPGs' EXIF/XMP metadata itself**

✅ **Verified:** the old `rdf-plugin/rdfexport.cpp` contains 49 ontology/metadata terms (`chs:Hardware`, `chs:EquipmentConfiguration`, `creator`, `orcid`…), 30 `XMP_SET` calls and Dublin Core / IPTC (`kDC`/`kIptc`) reads.

**This carried two costs:**

1. **Every ontology change required a C++ recompile.** Even the smallest change to the ontology forced editing and rebuilding the plugin.

2. **A single-source-of-truth violation.** The same facts were duplicated in three places at once: `kg-config.json`, `shared.ttl` and the plugin itself.

   ✅ **Verified:** the old version carries `kg-config.json` (project metadata) + `shared.ttl` (embedded TBox + metadata) + the plugin (ontology terms) together — a threefold duplication.

**A downstream symptom.** This coupling also showed in the output: the old final `.ttl` carried ontology declarations interleaved with the data and a multi-header, concatenated structure. (That structural mess was later addressed separately in change (B), the data correction — see [[RupeMagnaOnto-Plan2-Report]].)

**In short:** the plugin had mixed two responsibilities — "technical record" and "ontology" — which hurt both maintainability (recompile) and consistency (threefold duplication).

## 2. The decision (separation of concerns)

**The core idea:** separate the responsibilities. The plugin should write **only** the technical record produced during RTI processing (a small, ontology-neutral file). Everything ontological — coordinates, survey data, mappings, provenance modelling — is handled in a separate **Python KG Builder** layer. The ontology then **never requires a C++ recompile** again. This split mirrors ArCo's distinction between *denotative description* (machine-observed) and *context description* (asserted by the researcher).

**Where each responsibility lives — old vs new:**

| Concern | Old | New |
|---|---|---|
| Capture RelightLab's in-memory job record | C++ plugin (as RDF/TTL) | C++ plugin → `writeProvenanceJson` (ontology-neutral JSON) |
| Read JPG EXIF/XMP | C++ plugin (`XMP_SET`, `kDC`/`kIptc`) | Python KG Builder, from the source JPGs |
| Ontology / CHS-ODP mappings, provenance modelling | embedded in the C++ plugin | Python KG Builder + `shared.ttl` |
| Project metadata (author, licence, coordinates) | duplicated: `kg-config.json` + `shared.ttl` + plugin | single source: `enrich-metadata.json` |
| Final output | concatenated, multi-header `.ttl` | one `.ttl`, assembled in memory |
| Changing the ontology | edit + **recompile RDF plugin** the C++ plugin | edit Python / TTL, **no recompile** |

**Key decisions:**

| # | Decision | Status |
|---|---|---|
| 1 | The plugin emits a minimal, **ontology-neutral JSON**, not RDF/TTL | ✅ verified |
| 2 | The JSON follows the TTL naming convention: `F01RTI08-ptm.json` | ✅ verified |
| 3 | The plugin reuses RelightLab's own `Task::info()` + `RtiParameters::toJson()`, so new parameters appear automatically | ✅ verified |
| 4 | The plugin does **not** read JPG EXIF/XMP; the KG Builder reads those directly | ✅ verified (new automatic path) |
| 5 | **Never edit RelightLab directly** — all logic in the plugin, all wiring in `semRTI.py` | ⚠️ author's record |
| 6 | Project metadata comes from a **single source** (`enrich-metadata.json`); stamping the JPGs is a separate, optional menu item | ✅ verified |
| 7 | **No `section-b/c/d` intermediate files** — the KG Builder assembles in memory and writes one final `.ttl` | ✅ verified |
| 8 | **No incremental "add new RTIs only" mode** — at this scale a full rebuild is fast and always consistent | ⚠️ author's record |
| 9 | The **manual full-TTL mode is deliberately kept (frozen)** — still needed; only the automatic flow bypasses it | ✅ verified (old/new plugin ontology code identical; `metadataframe.cpp` byte-identical) |

**In short:** the plugin's job becomes "dump the in-memory technical record to disk" (C++, unavoidable); the ontology and graph building move to the Python KG Builder (no recompile). The manual full-TTL path remains, frozen, off to one side.

## 3. The new architecture

**Two distinct moments:**

- **The processing moment (RelightLab running)** — the plugin captures the facts that exist **only in memory** at export time (the RTI parameters, the job record) and writes them to disk. This **must be C++**, because that information vanishes when RelightLab closes.

- **Afterwards (graph building)** — the KG Builder reads those files plus the ontology and assembles the graph. **Python.**

The KG Builder is not a separate application — it is the "brain" living inside `semRTI`: the part that turns the JSON files plus the ontology into the graph.

**New Flow:**

```
RAW → Darktable → JPG (+ metadata) → RelightLab (+ RDF plugin)
                                          │
                                          ▼
               (per dataset) = info.json  +  F01RTI08-ptm.json
                                          │
                                          ▼
                                  KG Builder (Python)
                 (+ JPG technical EXIF, enrich-metadata.json,
                    ontology / shared.ttl, construct-*.sparql)
                                          │
                                          ▼
                          Single final Knowledge Graph (.ttl)
```

**Division of labour:**

| Layer | Language | Job | When |
|---|---|---|---|
| RDF plugin | C++ | Write the in-memory job record to disk as JSON | During RTI processing |
| KG Builder | Python | Read the JSON files + ontology → build the graph | Afterwards |


**Old vs new flow (in brief):**

| | Old | New |
|---|---|---|
| Plugin output | RDF/TTL (ontology embedded) | ontology-neutral JSON (`*-ptm.json`) |
| Intermediate files | section-c/d + cat concatenation | none (merged in memory) |
| Graph assembly | scattered / hand-glued | `_kg_build_final` (rdflib, single document) |
| Provenance (Section E) | inside the plugin's TTL | `construct-rti.sparql` + `*-ptm.json` |


**Files and what they hold:**

| File | Location | Contents |
|---|---|---|
| `info.json` | each dataset | RelightLab's **own** technical output (planes, quality, dimensions, colourspace, lights, materials) |
| `F01RTI08-ptm.json` | each dataset | the **plugin's** provenance record (uuid, parameters, software + version, timestamp) |
| `enrich-metadata.json` | semRTI | project constants (author, licence, site, coordinates) — single source |
| `shared.ttl` | semRTI | static ontology base (project / site / figures) — an **input**, not an intermediate |
| `construct-*.sparql` | semRTI | EXIF/JSON → triple templates (dataset / photos / rti) |
| final `.ttl` | semRTI output | the single, merged knowledge graph |

✅ **Verified:** `info.json` + `*-ptm.json` are present in each dataset; the `_kg_build_final` flow (EXIF → Section C/D [SPARQL Anything] → Section E [ptm.json] → merge with `shared.ttl` + `enrich-metadata`) exists in the code; `construct-rti.sparql` is new.

## 4. The concrete changes (file by file)

This section shows how the architectural decisions (Sections 2–3) landed in the code. There were two implementation phases: **Phase A** (code simplification) and **Phase B** (personal metadata to a single source).

**File-level changes — old vs new:**

| File | Old | New | Status |
|---|---|---|---|
| `rdf-plugin/rdfexport.cpp` | automatic output was RDF/TTL; read EXIF/XMP | `writeProvenanceJson` **added** (automatic = ontology-neutral JSON, reads no EXIF/XMP); the old TTL code is **frozen** | ✅ |
| `rdf-plugin/metadataframe.cpp` | manual metadata → TTL page | **byte-identical** (deliberately preserved) | ✅ |
| `kg-config.json` → `enrich-metadata.json` | project metadata (KG only) | **single source** (JPG + KG) + a `_note` description | ✅ |
| `semRTI.py` | embedded copy of the metadata; `_find_jpg_export_dir`, `_kg_pipeline`; duplicated open/confirm code | `_load_metadata` / `_metadata_ttl` / `_run_construct` / `_choose_dataset` / `_confirm`; no embedded copy | ✅ |
| `construct-rti.sparql` | **absent** | **new** — Section E (ptm.json provenance) | ✅ |
| `construct-dataset/photos.sparql` | personal metadata hard-coded | trimmed for injection (LICENSE placeholder, etc.) | ✅ |
| `shared.ttl` | personal metadata values embedded | values removed; comments "injected at build time from `enrich-metadata`" | ✅ |

**Phase A — code simplification:**

- The pattern repeated across Sections C/D/E ("read template → fill placeholder → run SPARQL Anything → clean up") was reduced to a single **`_run_construct`** driver.

- Dead code (`_find_jpg_export_dir`, `_kg_pipeline`) was deleted; the shared opening was reduced to `_choose_dataset` and the y/N confirmation to `_confirm`; the JPG logs were redirected to their own `jpg-metadata` folder.

**Phase B — personal metadata to a single source:**

- creator, ORCID, e-mail, affiliation, role, licence, coordinates/address were **stripped from the hard-coded copies** in `shared.ttl` and the three `construct-*.sparql` files; they are now **injected at build time from `enrich-metadata.json`** via `_metadata_ttl` (the modelling stays in the templates; a blank field is never written to the graph).

- ⚠️ **Author's record, consistent with observation:** after Phase B, a comparison against the old graph reported **7,563 triples identical**, with only two deliberate differences (a redundant ORCID `NamedIndividual` removed, and the single-sourced "Italy" country value). This snapshot was taken *before* the data correction; it is consistent in magnitude with the old pipeline measured today (~7,563), but that exact moment cannot be reproduced now.


## 5. The data-correction layer (summary + link)

Once the redesigned pipeline was in place (Sections 1–4), the second change was a set of **accuracy and hygiene fixes to the graph it produces** (25 June). This is the implementation of the "Plan 2 — Dataset Correction" tasks (T1–T12, V1–V6). **The full detail lives in a separate document: [[RupeMagnaOnto-Plan2-Report]].** Here I give only a summary and a link; I do not repeat it.

**Summary (what was done):**

| Group | Tasks | Result |
|---|---|---|
| Active root-fixes (pipeline source) | T1, T2 (`shared.ttl` TBox / `isSurveyOn`), T6 (data-driven `seriesMember`), T11 (data-driven `numberOfItems`), T12a (measurement datatype) | applied in the new output + verified |
| Verification (no code change) | T3, T4, T5 (pipeline already single-document), T9 (inverse properties), V1–V6 (6/6 PASS) | confirmed clean |
| Deferred / skipped by decision | T8 (interpretation → deferred), T10 (geometry → deferred), T12b (don't touch SHACL → skip) | documented |

**SHACL net result:** baseline `4 CONFORM / 4 VIOLATE` → corrected 2-session output **`7 CONFORM / 1 VIOLATE`** (the single remaining violation = T12b, deliberately out of scope).

**The key link (how the two changes join):** most of this data correction was made possible — and made durable — **by the new pipeline architecture**. For example, the "single clean document" (T3/T4/T5) is simply a natural consequence of `_kg_build_final` (Section 3); and because the fixes were made in the **pipeline source** rather than by hand in the final file, they persist on every rebuild.

**Data constraint:** all fixes were proven on 2 sessions (RTI-08, RTI-17); the full 24-session deliverable can only be regenerated once the source data is available.

For the details → [[RupeMagnaOnto-Plan2-Report]].

## 6. Current status & remaining work

**The redesign (A) is complete.** The items shown as "next / to-do" in the 20 June design report are now present in the code: the plugin's JSON writer, the Python KG Builder, the single-source `enrich-metadata.json`, the new menu, and the single final `.ttl`.

| Item | Status | Note |
|---|---|---|
| Plugin provenance JSON writer (`writeProvenanceJson`) | ✅ | present in `rdfexport.cpp` |
| KG Builder (JSON + ontology → single `.ttl`) | ✅ | `_kg_build_final` |
| Single-source `enrich-metadata.json` (JPG + KG) | ✅ | verified |
| New menu (Your metadata → JPG first; single final TTL; no incremental mode) | ✅ | verified |
| Manual full-TTL mode | ✅ kept | deliberately frozen |
| Plugin dropping the JSON **automatically** when an RTI finishes (auto-wire) | ✅ | the `*-ptm.json` files are produced (it works); the full auto-wiring was verified |


**Remaining on the data-correction (B) side:** T8 (interpretation) and T10 (geometry) → **deferred** by your decision; T12b (shape coverage of the RTI measurements) → **skipped** under the "don't touch SHACL" decision (documented). Detail: [[RupeMagnaOnto-Plan2-Report]].

**Data constraint (shared by both changes):** this copy holds only 2 sessions of source data (RTI-08, RTI-17). The architecture and the fixes were proven on these; the **full 24-session deliverable can only be regenerated once the source data is available.**
