# semRTI — Semantic RTI Knowledge Graph

> Turn RTI photographic survey data into a single, FAIR-compliant RDF/Turtle knowledge graph.

![semRTI terminal interface](01-pipeline/semRTI-interface.png)

semRTI is a self-contained, menu-driven pipeline that converts Reflectance
Transformation Imaging (RTI) survey data into a **FAIR-compliant RDF/Turtle
Knowledge Graph**, aligned to the [Cultural Heritage Survey Ontology Design
Pattern](https://github.com/odpa/patterns-repository/blob/master/CulturalHeritageSurvey/index.md)
(CHS-ODP) and [ArCo](http://wit.istc.cnr.it/arco). It documents the complete chain —
from raw photographic acquisition, through RTI model generation in
[RelightLab](https://github.com/cnr-isti-vclab/relight), to equipment configuration,
per-frame observations, processing provenance and authorship — in one
machine-readable file.

The reference dataset is the **Rupe Magna** petroglyph survey (Grosio, Lombardy,
Italy, September 2025): [**40 RTI acquisition sessions across 11 rock art figures
(F01–F11)**](https://github.com/e-huseyin/rupemagnaviewer).

> **Version 1.0.1 — what changed.** The RelightLab plugin no longer emits RDF.
> It now writes an **ontology-neutral provenance JSON**, and all ontology logic
> lives in a Python **KG Builder**. The result: the ontology can change with
> **no C++ recompile**, project metadata has a **single source of truth**
> (`enrich-metadata.json`), and the graph is assembled in memory into **one
> final `.ttl`** — no concatenated, multi-header intermediate files. See
> [Version.1.0.1-Report.md](Version.1.0.1-Report.md) for the full migration report.

---

## Architecture

The pipeline separates two responsibilities. A small **C++ plugin** captures the
facts that exist only in RelightLab's memory at export time (the RTI parameters,
the job record). Everything ontological — CHS-ODP mappings, coordinates, survey
modelling, provenance — is handled afterwards by the **Python KG Builder**.

```
RAW → Darktable → JPG (+ EXIF) → RelightLab (+ RDF plugin)
                                       │
                                       ▼
                  per dataset:  info.json  +  F01RTI08-ptm.json
                                       │
                                       ▼
                              KG Builder (Python)
              + JPG EXIF · enrich-metadata.json · shared.ttl
              · construct-{dataset,photos,rti}.sparql
                                       │
                                       ▼
                   Single final Knowledge Graph (.ttl)
```

| Layer | Language | Job | When |
|---|---|---|---|
| RDF plugin | C++ | Write RelightLab's in-memory job record to disk as JSON | During RTI processing |
| KG Builder | Python | Read the JSON files + ontology → build the graph | Afterwards |

---

## Requirements

| Tool | Version | Install |
|---|---|---|
| Python | 3.10+ | `brew install python3` |
| Rich | 13.x+ | `pip3 install rich` |
| rdflib | 6.x+ | `pip3 install rdflib` |
| Java | 11+ | `brew install openjdk` |
| exiftool | any | `brew install exiftool` |
| SPARQL Anything | 1.x | [Download JAR](https://github.com/SPARQL-Anything/sparql.anything/releases/tag/v1.1.0) → place in `01-pipeline/` as `sparql-anything.jar` |

> **Platform:** developed and tested on **macOS**. Linux should work with minor
> path adjustments. Windows is not supported. The *RDF Plugin Install* step
> additionally needs CMake, a C++ toolchain and Qt 6 (`brew install cmake qt@6 libomp`).

---

## Quick Start

**1. Fill in `enrich-metadata.json` first** (see below) — it is the single source
of your attribution and site metadata.

**2. Launch the menu:**

```bash
python3 01-pipeline/semRTI.py
```

On first launch the working tree is created automatically:

```
semRTI/
├── 01-pipeline/                ← scripts, ontology, templates, plugin
├── 02-datasets/                ← place RTI datasets here
│   └── <Site>/<Figure>/<Session>/
│       ├── jpg-export/         ← source images (stamped + read for EXIF)
│       └── ptm/                ← RelightLab output (info.json + *-ptm.json)
├── 03-outputs/
│   └── knowledge-graph/        ← final *.ttl + *-exif.json
└── 04-logs/
    ├── jpg-metadata/
    ├── knowledge-graph/
    └── rdf-plugin/
```

Organise datasets as `<Site>/<Figure>/<Session>/`. After processing an RTI in
RelightLab, each session folder holds RelightLab's `info.json` and the plugin's
`F01RTI08-ptm.json` provenance sidecar.

---

## `enrich-metadata.json` — single source of truth

`01-pipeline/enrich-metadata.json` holds **all** of your personal and project
metadata: author, ORCID, affiliation, licence, site name and coordinates. It
feeds **both** outputs — the optional JPG metadata stamping and the knowledge
graph — from one place.

```json
{
  "author": "Your Name",
  "role": "Your role / position",
  "email": "you@example.org",
  "orcid": "https://orcid.org/0000-0000-0000-0000",
  "affiliation": "Your institution",
  "license": "Licensed under CC BY 4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "site": "Your site name",
  "city": "City",
  "province": "Province / region",
  "country": "Country",
  "gps_lat": "00.000000",
  "gps_lon": "00.000000",
  "gps_alt": "000.0"
}
```

Only the field names shown are recognised. A blank field is simply **omitted** —
no empty value is ever written to the graph — and any unrecognised field is
ignored. Fill this in **before** running the menu.

---

## The menu

| # | Action | What it does |
|---|---|---|
| 1 | **Your metadata → JPG** | Stamps `enrich-metadata.json` fields (author, licence, location, GPS) into your JPGs via exiftool. Optional; for archiving and sharing. |
| 2 | **RDF Plugin Install** | Patches a cloned RelightLab source tree with the C++ plugin and builds it (`cmake` → `make`). Re-runnable; resets any previous patch first. |
| 3 | **Generate KG** | Pick a dataset folder and build the single final knowledge graph `.ttl`. |
| 4 | **Logs** | Browse timestamped logs for each pipeline stage. |

### What *Generate KG* does

1. **EXIF export** — `exiftool` writes per-image technical metadata to JSON.
2. **Dataset + photo triples** — `construct-dataset.sparql` and
   `construct-photos.sparql` run through SPARQL Anything to build the survey,
   dataset, photo and observation triples.
3. **RTI provenance** — `construct-rti.sparql` maps each `info.json` +
   `*-ptm.json` pair into RTI processing-provenance triples.
4. **Merge** — everything is merged in memory (rdflib) with the static
   `shared.ttl` and the injected `enrich-metadata.json` values, then serialised
   **once** to `03-outputs/knowledge-graph/<site>-knowledge-graph.ttl`.

---

## The knowledge graph

semRTI builds an ABox that instantiates the **CHS-ODP** survey pattern and reuses
**ArCo** for the cultural property and for denotative/context descriptions. The
schema (TBox) is **not** embedded in the data — it lives in
`rupemagna-rti-ontology.owl` (an application profile) plus the external
ontologies it imports, so the data file stays pure ABox.

### How the graph is assembled

| Layer | Source | Builds |
|---|---|---|
| **Static base** | `shared.ttl` | Project, site, agent, two equipment items, 14 measurement types, 6 units; the 11 figures + their dataset series; the RTI method. |
| **Dataset triples** | `construct-dataset.sparql` | Per session: Survey, AgentRole, EquipmentConfiguration (+ camera settings), ObservationCollection, Dataset, JPG/RAW Distributions. |
| **Photo triples** | `construct-photos.sparql` | Per frame: an Observation and its JPEG (and RAF) `PhotographicDocumentation` result, with file-size / width / height measurements. |
| **RTI provenance** | `construct-rti.sparql` | Per RTI output: the PTM/HSH Distribution (`dcat:Distribution` + `chs:Result`) and its processing parameters, from `info.json` + `*-ptm.json`. |

### ODP pattern (generic)

```
chs:CulturalHeritageProject
  └─ chs:hasSurvey ────────────────────► chs:CulturalHeritageSurvey
        ├─ chs:isSurveyOn ──────────────► chs:CulturalProperty
        ├─ chs:usesEquipmentConfiguration ► chs:EquipmentConfiguration
        │        └─ chs:usesEquipment ────► chs:Hardware
        └─ chs:hasObservationCollection ─► chs:ObservationCollection
                 └─ chs:hasMember ────────► chs:Observation
                          ├─ chs:hasFeatureOfInterest ► chs:FeatureOfInterest
                          └─ chs:hasResult ───────────► chs:Result
```

### Rupe Magna instance

```
rm-project:rupe-magna-rti                     chs:CulturalHeritageProject
  └─ chs:hasSurvey
       rm-survey:{session}                     chs:CulturalHeritageSurvey
         ├─ chs:isSurveyOn ──► rm-fig:{figure} , rm-site:rupe-magna   (figure + site)
         ├─ core:hasAgentRole ► rm-role:{session}-photographer
         ├─ chs:usesMethod ──► rm-method:rti
         ├─ tiapit:startTime / tiapit:endTime
         ├─ chs:usesEquipmentConfiguration
         │    rm-econf:{session}               chs:EquipmentConfiguration
         │      ├─ chs:usesEquipment ► rm-equip:rti-dome , rm-equip:fujifilm-xs20
         │      └─ a-dd:hasMeasurementCollection
         │           └─ ISO · aperture · shutter · focal length
         └─ chs:hasObservationCollection
              rm-ocoll:{session}               chs:ObservationCollection
                └─ chs:hasMember  (one per captured frame)
                     rm-obs:{frame}            chs:Observation
                       ├─ chs:hasFeatureOfInterest ► rm-fig:{figure}
                       └─ chs:hasResult
                            ├─ rm-photo:{frame}-jpg   (JPEG)
                            └─ rm-photo:{frame}-raw   (RAF — RAW+Fast Forge only)
```

The DCAT publication layer and the RTI processing output close the loop back to
the originating survey:

```
rm-data:{session}              dcat:Dataset
  ├─ dcat:inSeries ──────────► rm-series:{figure}
  ├─ dcat:distribution ──────► rm-dist:{session}-jpg   (image/jpeg)
  ├─ dcat:distribution ──────► rm-dist:{session}-raw   (image/x-fujifilm-raf)
  └─ prov:wasGeneratedBy ────► rm-survey:{session}

rm-dist:{session}-ptm          dcat:Distribution , chs:Result   ← info.json + *-ptm.json
  ├─ prov:wasGeneratedBy ────► rm-survey:{session}
  ├─ dct:created (UTC) · dct:identifier (uuid) · schema:width / height
  └─ a-dd:hasMeasurementCollection
       └─ planes · JPEG quality · basis type · web layout
          colour-profile mode · OpenLime · crop origin
```

### The key alignment bridge

The ODP expects `chs:CulturalProperty` / `chs:FeatureOfInterest` where the data
uses ArCo's `arco:ArchaeologicalProperty` (the site and the figures). Two
`rdfs:subClassOf` declarations in `rupemagna-rti-ontology.owl` make this OWL-valid:

```turtle
arco:ArchaeologicalProperty
    rdfs:subClassOf chs:CulturalProperty ;
    rdfs:subClassOf chs:FeatureOfInterest .
```

Without them, a reasoner would flag range violations on `chs:isSurveyOn`
(Survey → CulturalProperty) and `chs:hasFeatureOfInterest`.

### Application-profile ontology

`rupemagna-rti-ontology.owl` defines **no new classes or properties**. It imports
the CHS-ODP and the supporting ontologies, declares the alignment bridge above,
and adds OWL cardinality restrictions that document the expected shape of a
session — e.g. each Survey `isSurveyOn` ≥ 2 `ArchaeologicalProperty` (figure +
site), each `EquipmentConfiguration` uses exactly 2 `Hardware`, and each
`ObservationCollection` holds 48 `Observation` members (one per dome LED).

### Figures (F01–F11)

| Figure | Sessions | Sector | Name |
|---|---|---|---|
| F01 | RTI-01 – RTI-10 | AA | The Praying Figure with Spiral |
| F02 | RTI-11 – RTI-12 | B | The Praying Woman Figure |
| F03 | RTI-13 – RTI-18 | F | The Spiral Figure |
| F04 | RTI-19 – RTI-23 | L | The Warrior Figure with Shield |
| F05 | RTI-24 | L | The Second Warrior Figure |
| F06 | RTI-25 – RTI-26 | L | The Wild Boar Figure |
| F07 | RTI-27 – RTI-28 | Q | The Goat Figure with a Beard |
| F08 | RTI-29 – RTI-33 | Q | The Second Goat Figure |
| F09 | RTI-34 – RTI-35 | Q | The Map-like Figure |
| F10 | RTI-36 – RTI-38 | S | The Knight Figure |
| F11 | RTI-39 – RTI-40 | S | The Figure with a Square |

### Vocabularies

All project resources live under `https://w3id.org/rupemagna/resource/{type}/`
(`project`, `survey`, `dataset`, `distribution`, `observation`, `photo`,
`measurement`, `figure`, `equipment`, …). External vocabularies reused:

| Prefix | Ontology | Used for |
|---|---|---|
| `chs:` | CulturalHeritageSurvey ODP | Survey, EquipmentConfiguration, Observation, Result |
| `arco:` | ArCo | `ArchaeologicalProperty` — site and figures |
| `a-cd:` | ArCo context-description | `PhotographicDocumentation` |
| `a-dd:` | ArCo denotative-description | `Measurement`, `MeasurementCollection`, `MeasurementType` |
| `core:` | ArCo core | `AgentRole` |
| `dcat:` | DCAT | `Dataset`, `DatasetSeries`, `Distribution` |
| `dct:` | Dublin Core Terms | creator, license, format, created, spatial |
| `foaf:` | FOAF | `Person`, name, mbox |
| `geo:` | WGS84 Geo | lat, long, alt |
| `muapit:` · `roapit:` · `tiapit:` | MU · RO · TI profiles | units & values · agent roles · start/end time |
| `schema:` | Schema.org | equipment attributes, item count, version |
| `prov:` | PROV-O | `wasGeneratedBy` (output → survey) |

---

## Files in `01-pipeline/`

| File | Role |
|---|---|
| `semRTI.py` | The pipeline — interactive menu + KG Builder. |
| `enrich-metadata.json` | Single source of project/author metadata. |
| `shared.ttl` | Static ABox base (shared resources + figures). |
| `dataset-config.csv` | Session → figure → sector → name mapping (40 sessions). |
| `construct-dataset.sparql` · `construct-photos.sparql` · `construct-rti.sparql` | SPARQL Anything CONSTRUCT templates (dataset · photo · RTI provenance triples). |
| `rupemagna-rti-ontology.owl` · `CulturalHeritageSurvey.ttl` · `catalog-v001.xml` | Application-profile ontology and CHS-ODP pattern. |
| `rdf-plugin/` | C++ RelightLab plugin (`rdfexport.*`, `metadataframe.*`) — emits the provenance JSON. |
| `sparql-anything.jar` | SPARQL Anything engine (download separately). |

---

## Data availability

The survey scope documented in `dataset-config.csv` and `shared.ttl` is the full
campaign: **40 sessions, 11 figures**. This repository ships **two sample
sessions** (F01/RTI-08, F03/RTI-17) so the pipeline can be run end-to-end; the
complete deliverable can be regenerated once the full source data is available.

---

**Author:** Hüseyin Erdoğan · [ORCID 0000-0002-2965-0918](https://orcid.org/0000-0002-2965-0918)
**Affiliation:** Alma Mater Studiorum – Università di Bologna
**License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
**Version:** 1.0.1 · June 2026
