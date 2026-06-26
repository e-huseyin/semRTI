
# semRTI — Semantic RTI Knowledge Graph

![semRTI terminal interface](01-pipeline/semRTI-interface.png)


## Overview

semRTI converts RTI photographic survey data into a **FAIR-compliant RDF/Turtle Knowledge Graph**, aligned to the [Cultural Heritage Survey Ontology Design Pattern](https://github.com/odpa/patterns-repository/blob/master/CulturalHeritageSurvey/index.md) (CHS-ODP).

The graph documents **40 RTI acquisition sessions** across **11 rock art figures** (F01–F11) at the Rupe Magna petroglyph site (Grosio, Lombardy, Italy), September 2025. It covers the complete documentation chain from raw photographic acquisition through RTI model generation, encoding equipment configuration, per-frame observations, provenance, and authorship in a single machine-readable Turtle file.

---

> **Platform:** Developed and tested on macOS. Linux should work with minor path adjustments. Windows is not yet supported.

---

## Requirements

| Tool | Version | Install |
|---|---|---|
| Python | 3.10+ | `brew install python3` |
| Rich | 13.x+ | `pip3 install rich` |
| Java | 11+ | `brew install openjdk` |
| exiftool | any | `brew install exiftool` |
| SPARQL Anything | 1.x | [Download JAR](https://github.com/SPARQL-Anything/sparql.anything/releases/tag/v1.1.0) → and place it inside `01-pipeline/` folder |

---
## Before anything else: `enrich-metadata.json`

`enrich-metadata.json` (in `01-pipeline/`) is the **single source of truth** for your personal and project metadata: author, ORCID, affiliation, licence, site name, and coordinates. **Fill it in first.** Open the file and replace the values with your own:

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

Why this file matters: it feeds **both** outputs of the pipeline from a single place —

- **(optional) the JPG metadata stamping** — menu option *Your metadata → JPG*, and
- **the knowledge graph**, which draws on the same attribution and provenance details.

Only the field names shown above are recognised. Any field left blank is simply not written, and any unrecognised field is ignored. So make sure your details are actually saved in this file **before** running the menu: if it is missing or empty, the corresponding output will not carry your metadata.

---
## Quick Start

```bash
python3 01-pipeline/semRTI.py
```

On first launch, the following structure is created automatically:

```
semRTI/
├── 01-pipeline/          ← scripts and ontology files
├── 02-datasets/          ← created on first run
│   └── Site Name/
│       └── Object-01/
│           └── RTI-01/
│               ├── raw/          ← original camera RAW files
│               ├── jpg/          ← original camera JPEG files
│               └── jpg-export/   ← RAW to JPEG output
├── 03-outputs/
│   └── knowledge-graph/  ← created on first run
└── 04-logs/
    ├── jpg-metadata/     ← created on first run
    ├── knowledge-graph/  ← created on first run
    └── rdf-plugin/       ← created on first run
```

Place your RTI dataset folders under `02-datasets/` following the same folder structure.

---


## Knowledge Graph Pipeline


```
                 RAW Images
                     │
                     ▼
                 Darktable
                     │
                     ▼
               JPEG + EXIF Metadata
                     │
                     ▼
                 RelightLab
                     │
                     ├── info.json
                     └── *-ptm.json
                             │
                             ▼
               Python Knowledge Graph Builder
                             │
                             ├── shared.ttl
                             ├── SPARQL CONSTRUCT
                             ├── EXIF extraction
                             ├── *-ptm.json
                             ├── RDF merge
                                       ▼
                         Final RDF Knowledge Graph .ttl
```


---


**Author:** Hüseyin Erdoğan · [ORCID 0000-0002-2965-0918](https://orcid.org/0000-0002-2965-0918)  
**Affiliation:** Alma Mater Studiorum – Università di Bologna  
**License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
**Version:** 1.0 · 2026-05-14
