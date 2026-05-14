#!/usr/bin/env python3
"""SemRTI — Semantic RTI Knowledge Graph pipeline (standalone)"""

import os, sys, json, glob, subprocess, re, shutil, logging, urllib.parse
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
console = Console()

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                          USER CONFIGURATION                                ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  Edit the values in this section before first use.                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

KG_AUTHOR      = "Hüseyin Erdoğan"
KG_ROLE        = "Post-Lauream Research Fellow"
KG_EMAIL       = "huseyin.erdogan@unibo.it"
KG_ORCID       = "https://orcid.org/0000-0002-2965-0918"
KG_AFFILIATION = "Alma Mater Studiorum – Università di Bologna"
KG_LICENSE     = "Licensed under CC BY 4.0"
KG_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

KG_SITE     = "Rupe Magna"
KG_CITY     = "Grosio"
KG_PROVINCE = "Lombardy"
KG_COUNTRY  = "Italy"
KG_GPS_LAT  = "46.292692"
KG_GPS_LON  = "10.264064"
KG_GPS_ALT  = "679.9"

# ── end of USER CONFIGURATION ──────────────────────────────────────────────────

# semRTI/ klasörü 01-pipeline/ içinde; proje kökü iki üst seviyede
DATASETS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '02-datasets'))
OUTPUTS_DIR  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '03-outputs'))
LOGS_DIR     = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '04-logs'))

KG_CONFIG_FILE      = os.path.join(SCRIPT_DIR, 'kg-config.json')
SPARQL_ANYTHING_JAR = os.path.join(SCRIPT_DIR, 'sparql-anything.jar')
TEMPLATE_DATASET    = os.path.join(SCRIPT_DIR, 'construct-dataset.sparql')
TEMPLATE_PHOTOS     = os.path.join(SCRIPT_DIR, 'construct-photos.sparql')
KG_DATASET_CSV      = os.path.join(SCRIPT_DIR, 'dataset-config.csv')
KG_SHARED_TTL       = os.path.join(SCRIPT_DIR, 'shared.ttl')
KG_OUTPUTS_DIR      = os.path.join(OUTPUTS_DIR, 'knowledge-graph')

RDF_PLUGIN_DIR   = os.path.join(SCRIPT_DIR, 'rdf-plugin')
RDF_PLUGIN_FILES = ['rdfexport.h', 'rdfexport.cpp', 'metadataframe.h', 'metadataframe.cpp']

LOGO = [
    r" ██████╗ ███████╗███╗   ███╗██████╗ ████████╗██╗",
    r"██╔════╝ ██╔════╝████╗ ████║██╔══██╗╚══██╔══╝██║",
    r"███████╗ █████╗  ██╔████╔██║██████╔╝   ██║   ██║",
    r"╚════██╗ ██╔══╝  ██║╚██╔╝██║██╔══██╗   ██║   ██║",
    r" ██████╔╝███████╗██║ ╚═╝ ██║██║  ██║   ██║   ██║",
    r" ╚═════╝ ╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝",
]

TAGLINE = "Semantic RTI Knowledge Graph"
VERSION = "v1.0.0"

MENU = [
    ("Knowledge Graph",    "EXIF → RDF / Turtle"),
    ("RDF Plugin Install", "Patch & build RelightLab"),
    ("Logs",               "Browse pipeline logs"),
]

_TREE_EXCLUDE = {'raw', 'jpg', 'jpg-export', '.ds_store'}


def _tree_excluded(name):
    nl = name.lower()
    return (nl.startswith('.') or
            nl in _TREE_EXCLUDE or
            nl.startswith('jpg-export') or
            nl.startswith('relight-cli-'))


# ── Logging ────────────────────────────────────────────────────────────────────

def _make_logger(module, label=''):
    log_dir = os.path.join(LOGS_DIR, module)
    os.makedirs(log_dir, exist_ok=True)
    ts   = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    safe = re.sub(r'[^\w\-]', '_', label)[:40]
    filename = f"{ts}_{safe}.log" if safe else f"{ts}.log"
    log_path = os.path.join(log_dir, filename)

    logger = logging.getLogger(f'semrti.{module}.{ts}')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)-7s %(message)s',
                                      datefmt='%H:%M:%S'))
    logger.addHandler(fh)
    logger.info(f"Log: {log_path}")
    return logger, log_path


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _ask(prompt, default=''):
    """Single-line input. Returns None when user types Q/B or presses Ctrl-C."""
    try:
        val = input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        return None
    if val.upper() in ('Q', 'B'):
        return None
    return val if val else default


def _wait_enter(msg="  Press Enter to continue (Q to go back)"):
    try:
        input(msg)
    except (KeyboardInterrupt, EOFError):
        pass


# ── Dataset tree browser ───────────────────────────────────────────────────────

def _build_dataset_tree(root, max_depth=3):
    items = []

    def walk(path, prefix, parent_prefix, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(
                [e for e in os.scandir(path)
                 if e.is_dir() and not _tree_excluded(e.name)],
                key=lambda e: e.name
            )
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            is_last   = (i == len(entries) - 1)
            connector = '└─ ' if is_last else '├─ '
            items.append((prefix + connector, entry.name, entry.path))
            child_prefix = parent_prefix + ('   ' if is_last else '│  ')
            walk(entry.path, child_prefix, child_prefix, depth + 1)

    walk(root, '', '', 1)
    return items


def _dataset_picker(title, subtitle=''):
    tree_items = _build_dataset_tree(DATASETS_DIR)

    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]  [dim]{subtitle}[/dim]")
    console.print(f"  [dim]Root: {DATASETS_DIR}[/dim]")
    console.print()

    if not tree_items:
        console.print("  [yellow]No datasets found in 02-datasets/[/yellow]")
        console.print()
    else:
        for i, (prefix, name, _) in enumerate(tree_items, 1):
            console.print(
                f"  [bold cyan]{i:>3}.[/bold cyan]  [dim]{prefix}[/dim][white]{name}[/white]"
            )
        console.print()

    console.print("  [dim]Type a number to select, or type a path directly. Q to cancel.[/dim]")
    val = _ask("  Dataset: ")
    if val is None:
        return ''

    try:
        idx = int(val) - 1
        if 0 <= idx < len(tree_items):
            return os.path.relpath(tree_items[idx][2], DATASETS_DIR)
    except ValueError:
        pass

    return val.replace('\\ ', ' ').strip().strip("'\"")


# ── Dataset helpers ────────────────────────────────────────────────────────────

def _find_jpg_export_dir(base):
    base = os.path.abspath(base)
    candidates = []
    for search_root in [base] + [os.path.join(base, c)
                                  for c in sorted(os.listdir(base))
                                  if os.path.isdir(os.path.join(base, c))]:
        try:
            for entry in sorted(os.listdir(search_root)):
                if entry == 'jpg-export' or entry.startswith('jpg-export-'):
                    full = os.path.join(search_root, entry)
                    if os.path.isdir(full):
                        candidates.append(full)
        except (PermissionError, NotADirectoryError):
            pass
        if candidates:
            break
    if not candidates:
        return None
    exact = [c for c in candidates if os.path.basename(c) == 'jpg-export']
    return exact[0] if exact else candidates[0]


# ── Knowledge Graph pipeline ───────────────────────────────────────────────────

def _kg_load_config():
    default = {
        "author":      KG_AUTHOR,
        "role":        KG_ROLE,
        "email":       KG_EMAIL,
        "orcid":       KG_ORCID,
        "affiliation": KG_AFFILIATION,
        "license":     KG_LICENSE,
        "license_url": KG_LICENSE_URL,
        "site":        KG_SITE,
        "city":        KG_CITY,
        "province":    KG_PROVINCE,
        "country":     KG_COUNTRY,
        "gps_lat":     KG_GPS_LAT,
        "gps_lon":     KG_GPS_LON,
        "gps_alt":     KG_GPS_ALT,
    }
    if not os.path.exists(KG_CONFIG_FILE):
        with open(KG_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=2, ensure_ascii=False)
        return default
    try:
        with open(KG_CONFIG_FILE, encoding='utf-8') as f:
            cfg = json.load(f)
        for k, v in default.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return default


def _to_file_uri(path):
    return 'file://' + urllib.parse.quote(os.path.abspath(path), safe='/:')


def _kg_step1_metadata(dataset_dir, site_name, cfg, logger):
    author      = cfg.get('author', '')
    role        = cfg.get('role', '')
    email       = cfg.get('email', '')
    orcid       = cfg.get('orcid', '')
    affiliation = cfg.get('affiliation', '')
    license_str = cfg.get('license', 'Licensed under CC BY 4.0')
    license_url = cfg.get('license_url', 'https://creativecommons.org/licenses/by/4.0/')
    city        = cfg.get('city', '')
    province    = cfg.get('province', '')
    country     = cfg.get('country', '')
    gps_lat     = cfg.get('gps_lat', '')
    gps_lon     = cfg.get('gps_lon', '')
    gps_alt     = cfg.get('gps_alt', '')

    total    = 0
    jpg_dirs = []

    for f_dir in sorted(glob.glob(os.path.join(dataset_dir, 'F*/'))):
        if not os.path.isdir(f_dir):
            continue
        f_name = os.path.basename(f_dir.rstrip('/'))
        for rti_dir in sorted(glob.glob(os.path.join(f_dir, 'RTI-*/'))):
            rti_name = os.path.basename(rti_dir.rstrip('/'))
            try:
                for entry in sorted(os.listdir(rti_dir)):
                    if entry == 'jpg-export' or entry.startswith('jpg-export-'):
                        full = os.path.join(rti_dir, entry)
                        if os.path.isdir(full):
                            jpg_dirs.append((f_name, rti_name, full))
            except (PermissionError, NotADirectoryError):
                pass
            jpg_only = os.path.join(rti_dir, 'jpg')
            if os.path.isdir(jpg_only):
                jpg_dirs.append((f_name, rti_name, jpg_only))

    if not jpg_dirs:
        for rti_dir in sorted(glob.glob(os.path.join(dataset_dir, 'RTI-*/'))):
            rti_name = os.path.basename(rti_dir.rstrip('/'))
            try:
                for entry in sorted(os.listdir(rti_dir)):
                    if entry == 'jpg-export' or entry.startswith('jpg-export-'):
                        full = os.path.join(rti_dir, entry)
                        if os.path.isdir(full):
                            jpg_dirs.append(('', rti_name, full))
            except (PermissionError, NotADirectoryError):
                pass
            jpg_only = os.path.join(rti_dir, 'jpg')
            if os.path.isdir(jpg_only):
                jpg_dirs.append(('', rti_name, jpg_only))

    if not jpg_dirs:
        dirs_to_write = []
        try:
            for entry in sorted(os.listdir(dataset_dir)):
                if entry == 'jpg-export' or entry.startswith('jpg-export-'):
                    full = os.path.join(dataset_dir, entry)
                    if os.path.isdir(full):
                        dirs_to_write.append(full)
        except (PermissionError, NotADirectoryError):
            pass
        jpg_only = os.path.join(dataset_dir, 'jpg')
        if os.path.isdir(jpg_only):
            dirs_to_write.append(jpg_only)
        if not dirs_to_write:
            dirs_to_write.append(dataset_dir)
        for d in dirs_to_write:
            jpg_dirs.append(('', os.path.basename(dataset_dir), d))

    for f_name, rti_name, jpg_dir in jpg_dirs:
        label = (f"{site_name} - [{f_name}] - [{rti_name}]"
                 if f_name else f"{site_name} - [{rti_name}]")

        cmd = ['exiftool', '-overwrite_original', '-P', '-m', '-q',
               '-i', '.*', '-ext', 'jpg',
               f'-Title={label}',
               f'-XMP-dc:title={label}',
               f'-Description={label}',
               f'-XMP-dc:description={label}',
               f'-Caption-Abstract={label}',
               f'-Keywords=RTI, {site_name}, FAIR data, ArCo, {f_name}/{rti_name}',
               f'-XMP-dc:subject=RTI, {site_name}, FAIR data, ArCo',
               f'-Artist={author}',
               f'-By-line={author}',
               f'-XMP-dc:creator={author}',
               f'-XMP-photoshop:AuthorsPosition={role}',
               f'-Credit={author} / {affiliation}',
               f'-XMP-photoshop:Credit={author} / {affiliation}',
               f'-Copyright=© 2025 {author}',
               f'-UsageTerms={license_str}',
               f'-XMP-dc:rights={license_str}',
               f'-XMP-xmpRights:UsageTerms={license_str}',
               '-XMP-xmpRights:Marked=True',
               f'-XMP-xmpRights:WebStatement={license_url}',
               f'-XMP-plus:LicensorURL={orcid}',
               f'-CreatorWorkEmail={email}',
               f'-CreatorWorkURL={orcid}',
               f'-XMP-iptcExt:OrganisationInImageName={affiliation}',
               f'-City={city}',
               f'-XMP-photoshop:City={city}',
               f'-Province-State={province}',
               f'-XMP-photoshop:State={province}',
               f'-Country={country}',
               f'-XMP-photoshop:Country={country}',
               f'-Sub-location={site_name}',
               '-IPTCDigest=',
               jpg_dir]

        if gps_lat:
            cmd += [f'-GPSLatitude={gps_lat}', '-GPSLatitudeRef=N']
        if gps_lon:
            cmd += [f'-GPSLongitude={gps_lon}', '-GPSLongitudeRef=E']
        if gps_alt:
            cmd += [f'-GPSAltitude={gps_alt}', '-GPSAltitudeRef=0']

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"exiftool warning for {jpg_dir}: {result.stderr.strip()}")

        n = len(glob.glob(os.path.join(jpg_dir, '*.[Jj][Pp][Gg]')))
        total += n
        disp = f"{f_name}/{rti_name}" if f_name else rti_name
        print(f"           {disp} — {n} files")
        logger.info(f"Metadata written: {disp}  ({n} files)")

    return total


def _kg_step2_exif_export(dataset_dir, exif_json, logger):
    cmd = ['exiftool', '-j', '-r',
           '-i', 'resources',
           '-SourceFile', '-FileName', '-CreateDate', '-FileSize',
           '-ImageWidth', '-ImageHeight',
           '-ISO', '-FNumber', '-ExposureTime', '-FocalLength',
           dataset_dir]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"exiftool export failed: {result.stderr.strip()}")
        return 0

    with open(exif_json, 'w', encoding='utf-8') as f:
        f.write(result.stdout)

    try:
        count = len(json.loads(result.stdout))
    except Exception:
        count = 0
    logger.info(f"EXIF export: {count} records → {exif_json}")
    return count


def _kg_step3_section_c(exif_json, output_c, logger):
    if not os.path.exists(TEMPLATE_DATASET):
        logger.error(f"Template not found: {TEMPLATE_DATASET}"); return False
    if not os.path.exists(KG_DATASET_CSV):
        logger.error(f"dataset-config.csv not found: {KG_DATASET_CSV}"); return False

    with open(TEMPLATE_DATASET, encoding='utf-8') as f:
        query = f.read()
    query = query.replace('EXIF_LOCATION_PLACEHOLDER', _to_file_uri(exif_json))
    query = query.replace('CSV_LOCATION_PLACEHOLDER',  _to_file_uri(KG_DATASET_CSV))

    tmp = os.path.join(SCRIPT_DIR, '_tmp-construct-dataset.sparql')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(query)

    result = subprocess.run(
        ['java', '-jar', SPARQL_ANYTHING_JAR, '-q', tmp, '-o', output_c],
        capture_output=True, text=True
    )
    try:
        os.remove(tmp)
    except Exception:
        pass

    if result.returncode != 0:
        logger.error(f"SPARQL Anything (C) failed:\n{result.stderr.strip()}")
        return False
    logger.info(f"Section C → {output_c}")
    return True


def _kg_step4_section_d(exif_json, output_d, logger):
    if not os.path.exists(TEMPLATE_PHOTOS):
        logger.error(f"Template not found: {TEMPLATE_PHOTOS}"); return False

    with open(TEMPLATE_PHOTOS, encoding='utf-8') as f:
        query = f.read()
    query = query.replace('EXIF_LOCATION_PLACEHOLDER', _to_file_uri(exif_json))

    tmp = os.path.join(SCRIPT_DIR, '_tmp-construct-photos.sparql')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(query)

    result = subprocess.run(
        ['java', '-jar', SPARQL_ANYTHING_JAR, '-q', tmp, '-o', output_d],
        capture_output=True, text=True
    )
    try:
        os.remove(tmp)
    except Exception:
        pass

    if result.returncode != 0:
        logger.error(f"SPARQL Anything (D) failed:\n{result.stderr.strip()}")
        return False
    logger.info(f"Section D → {output_d}")
    return True


def _kg_step5_merge(output_c, output_d, output_final, logger):
    if not os.path.exists(KG_SHARED_TTL):
        logger.error(f"shared.ttl not found: {KG_SHARED_TTL}"); return -1

    with open(output_final, 'w', encoding='utf-8') as f_out:
        for src in [KG_SHARED_TTL, output_c, output_d]:
            if os.path.exists(src):
                with open(src, encoding='utf-8') as f_in:
                    f_out.write(f_in.read())
            else:
                logger.warning(f"Source missing, skipping: {src}")

    try:
        import rdflib
        g = rdflib.Graph()
        g.parse(output_final, format='turtle')
        count = len(g)
        logger.info(f"Merge: {count} triples → {output_final}")
        return count
    except ImportError:
        logger.warning("rdflib not installed — pip3 install rdflib")
        return -1
    except Exception as e:
        logger.warning(f"Triple count error: {e}")
        return -1


def _kg_step6_section_e(dataset_dir, output_final, output_final_e, logger):
    shutil.copy(output_final, output_final_e)
    ttl_files = []
    for root, dirs, files in os.walk(dataset_dir):
        for fname in sorted(files):
            if re.match(r'(?i)^(ptm|hsh|rbf|bln)[^/]*\.ttl$', fname) or \
               re.match(r'RTI-.*-(PTM|HSH)\.ttl$', fname) or \
               re.match(r'^[A-Z]+\d+RTI\d+(PTM|HSH|RBF|BLN)\.ttl$', fname) or \
               re.match(r'^[A-Z]+\d+RTI\d+-(ptm|hsh|rbf|bln)[a-zA-Z0-9\-]*\.ttl$', fname, re.IGNORECASE):
                ttl_files.append(os.path.join(root, fname))

    if not ttl_files:
        logger.info("Section E: no RTI sidecar TTLs found — skipping")
        return 0

    with open(output_final_e, 'a', encoding='utf-8') as f_out:
        for ttl_path in sorted(ttl_files):
            with open(ttl_path, encoding='utf-8') as f_in:
                f_out.write(f_in.read())
            disp = f"{os.path.basename(os.path.dirname(ttl_path))}/{os.path.basename(ttl_path)}"
            print(f"           {disp}")
            logger.info(f"Section E: {disp}")

    try:
        import rdflib
        g = rdflib.Graph()
        g.parse(output_final_e, format='turtle')
        count = len(g)
        logger.info(f"Section E: {len(ttl_files)} file(s), {count} triples → {output_final_e}")
        return count
    except ImportError:
        return -1
    except Exception as e:
        logger.warning(f"Triple count error: {e}")
        return -1


def _kg_pipeline(dataset_dir, site_name, cfg, logger):
    safe_site = re.sub(r'[^\w\-]', '-', site_name).lower().strip('-')
    os.makedirs(KG_OUTPUTS_DIR, exist_ok=True)

    exif_json      = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-exif.json')
    output_c       = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-section-c.ttl')
    output_d       = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-section-d.ttl')
    output_final   = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-complete.ttl')
    output_final_e = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-final.ttl')

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  RTI Knowledge Graph Pipeline — {site_name}")
    print(f"  Dataset : {dataset_dir}")
    print(sep)

    print("\n[1/6] Writing EXIF/XMP/IPTC metadata into JPEGs...")
    logger.info("=== Step 1 — Writing metadata ===")
    total = _kg_step1_metadata(dataset_dir, site_name, cfg, logger)
    print(f"      → {total} JPEG files updated")

    print("\n[2/6] Exporting EXIF to JSON...")
    logger.info("=== Step 2 — Exporting EXIF ===")
    count = _kg_step2_exif_export(dataset_dir, exif_json, logger)
    print(f"      → {count} records")

    print("\n[3/6] Generating Section C (per-session triples)...")
    logger.info("=== Step 3 — Section C ===")
    ok_c = _kg_step3_section_c(exif_json, output_c, logger)
    print(f"      → {'OK' if ok_c else 'FAILED'}")

    print("\n[4/6] Generating Section D (per-photo triples)...")
    logger.info("=== Step 4 — Section D ===")
    ok_d = _kg_step4_section_d(exif_json, output_d, logger)
    print(f"      → {'OK' if ok_d else 'FAILED'}")

    print("\n[5/6] Merging into final Knowledge Graph...")
    logger.info("=== Step 5 — Merge ===")
    triples = _kg_step5_merge(output_c, output_d, output_final, logger)
    t_str = f"{triples} triples" if triples >= 0 else "done"
    print(f"      → {t_str}")

    print("\n[6/6] Collecting Section E (RTI sidecar TTLs)...")
    logger.info("=== Step 6 — Section E ===")
    triples_e = _kg_step6_section_e(dataset_dir, output_final, output_final_e, logger)
    te_str = f"{triples_e} triples" if triples_e >= 0 else "done"
    print(f"      → {te_str}")

    print(f"\n{sep}")
    print(f"  Done → {output_final_e}")
    print(f"{sep}\n")
    logger.info("=== Pipeline complete ===")


def run_knowledge_graph():
    console.clear()
    cfg = _kg_load_config()

    dataset_raw = _dataset_picker("KNOWLEDGE GRAPH",
                                  "·  EXIF → RDF/Turtle  ·  6-step semantic pipeline")
    if not dataset_raw:
        return

    dataset_raw = dataset_raw.replace('\\ ', ' ')
    if os.path.isabs(dataset_raw):
        dataset_dir = os.path.normpath(dataset_raw)
    else:
        dataset_dir = os.path.join(DATASETS_DIR, dataset_raw)

    site_name = cfg.get('site', 'dataset')

    missing = []
    for dep in ['exiftool', 'java']:
        if subprocess.run(['which', dep], capture_output=True).returncode != 0:
            missing.append(dep)
    if not os.path.exists(SPARQL_ANYTHING_JAR):
        missing.append('sparql-anything.jar')
    if not os.path.isdir(dataset_dir):
        missing.append(f'dataset not found: {dataset_dir}')

    if missing:
        console.print()
        console.rule("[bold red]KNOWLEDGE GRAPH  ·  Prerequisites missing[/bold red]")
        for m in missing:
            console.print(f"  [red][!][/red]  {m}")
        _wait_enter()
        return

    safe_site       = re.sub(r'[^\w\-]', '-', site_name).lower().strip('-')
    complete_ttl    = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-complete.ttl')
    step6_available = os.path.exists(complete_ttl)

    console.clear()
    console.print()
    console.rule(f"[bold cyan]KNOWLEDGE GRAPH[/bold cyan]  [dim]·  {site_name}[/dim]")
    console.print(f"  [dim]Dataset : {dataset_dir}[/dim]")
    console.print(f"  [dim]Site    : {site_name}[/dim]")
    console.print()
    console.print("  [bold cyan]1.[/bold cyan]  Full pipeline  [dim](steps 1–6, rewrites EXIF + rebuilds KG)[/dim]")
    if step6_available:
        console.print("  [bold cyan]2.[/bold cyan]  Collect RTI sidecars only  [dim](step 6, appends new TTL sidecars)[/dim]")
    else:
        console.print(f"  [dim]2.  (not available — {os.path.basename(complete_ttl)} not found)[/dim]")
    console.print()

    val = _ask("  Select (1/2, Q to cancel): ")
    if val is None:
        return
    if val == '1':
        mode = 'full'
    elif val == '2' and step6_available:
        mode = 'step6'
    else:
        return

    logger, log_path = _make_logger('knowledge-graph', site_name)
    logger.info(f"Dataset: {dataset_dir}")
    logger.info(f"Site:    {site_name}")
    logger.info(f"Mode:    {mode}")

    console.clear()
    console.print()
    console.rule(f"[bold cyan]KNOWLEDGE GRAPH[/bold cyan]  [dim]·  {site_name}[/dim]")
    console.print(f"  [dim]Dataset : {dataset_dir}[/dim]")
    console.print(f"  [dim]Site    : {site_name}[/dim]")
    console.print(f"  [dim]Log     : {os.path.basename(log_path)}[/dim]")
    console.rule(style="dim")

    try:
        if mode == 'step6':
            output_final_e = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-final.ttl')
            sep = "=" * 55
            print(f"\n{sep}")
            print(f"  RTI Knowledge Graph — Collect sidecars — {site_name}")
            print(f"  Base : {complete_ttl}")
            print(sep)
            print("\n[6/6] Collecting Section E (RTI sidecar TTLs)...")
            logger.info("=== Step 6 only — Section E ===")
            triples_e = _kg_step6_section_e(dataset_dir, complete_ttl, output_final_e, logger)
            te_str = f"{triples_e} triples" if triples_e >= 0 else "done"
            print(f"      → {te_str}")
            print(f"\n{sep}")
            print(f"  Done → {output_final_e}")
            print(f"{sep}\n")
            logger.info("=== Step 6 complete ===")
        else:
            _kg_pipeline(dataset_dir, site_name, cfg, logger)
    except Exception as e:
        console.print(f"\n  [red][!] Error: {e}[/red]")
        logger.error(str(e), exc_info=True)

    _wait_enter()


# ── RDF Plugin Install ─────────────────────────────────────────────────────────

def _patch_cmake(cmake_path):
    with open(cmake_path, encoding='utf-8') as f:
        content = f.read()

    modified = False

    if 'metadataframe.h' not in content:
        new_content = re.sub(
            r'(set\s*\(\s*RELIGHT_HEADERS\b.*?)(^\))',
            r'\1    metadataframe.h\n    rdfexport.h\n)',
            content, flags=re.DOTALL | re.MULTILINE
        )
        if new_content != content:
            content = new_content
            modified = True
        else:
            print("      [!] CMakeLists.txt RELIGHT_HEADERS — anchor not found, skipping")

    if 'metadataframe.cpp' not in content:
        new_content = re.sub(
            r'(set\s*\(\s*RELIGHTLAB_SOURCES\b.*?)(^\))',
            r'\1    metadataframe.cpp\n    rdfexport.cpp\n)',
            content, flags=re.DOTALL | re.MULTILINE
        )
        if new_content != content:
            content = new_content
            modified = True
        else:
            print("      [!] CMakeLists.txt RELIGHTLAB_SOURCES — anchor not found, skipping")

    if modified:
        with open(cmake_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return modified


def _patch_mainwindow_h(h_path):
    with open(h_path, encoding='utf-8') as f:
        content = f.read()

    modified = False

    if 'class MetadataFrame;' not in content:
        if 'class QueueFrame;' in content:
            content = content.replace(
                'class QueueFrame;',
                'class QueueFrame;\nclass MetadataFrame;'
            )
            modified = True
        else:
            print("      [!] mainwindow.h: 'class QueueFrame;' not found — forward decl skipped")

    if 'rtiFrame()' not in content:
        if 'public slots:' in content:
            content = content.replace(
                'public slots:',
                '\t// Returns RTI export frame so MetadataFrame can read processing parameters.\n'
                '\tRtiFrame *rtiFrame() const { return rti_frame; }\n\npublic slots:'
            )
            modified = True
        else:
            print("      [!] mainwindow.h: 'public slots:' not found — rtiFrame() skipped")

    if 'MetadataFrame *metadata_frame' not in content:
        if 'QueueFrame *queue_frame = nullptr;' in content:
            content = content.replace(
                'QueueFrame *queue_frame = nullptr;',
                'QueueFrame *queue_frame = nullptr;\n\tMetadataFrame *metadata_frame = nullptr;'
            )
            modified = True
        else:
            print("      [!] mainwindow.h: queue_frame member not found — member skipped")

    if modified:
        with open(h_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return modified


def _patch_mainwindow_cpp(cpp_path):
    with open(cpp_path, encoding='utf-8') as f:
        content = f.read()

    modified = False

    if '#include "metadataframe.h"' not in content:
        if '#include "queueframe.h"' in content:
            content = content.replace(
                '#include "queueframe.h"',
                '#include "queueframe.h"\n#include "metadataframe.h"'
            )
            modified = True
        else:
            print("      [!] mainwindow.cpp: queueframe.h include not found — include skipped")

    if 'new MetadataFrame' not in content:
        if 'queue_frame = new QueueFrame' in content:
            content = content.replace(
                'queue_frame = new QueueFrame',
                'metadata_frame = new MetadataFrame(this);\n\tqueue_frame = new QueueFrame'
            )
            modified = True
        else:
            print("      [!] mainwindow.cpp: QueueFrame constructor not found — MetadataFrame init skipped")

    if 'Metadata' not in content or 'addTab' not in content or 'metadata_frame' not in content:
        if 'queue_frame, tr("Queue")' in content:
            content = content.replace(
                'queue_frame, tr("Queue")',
                'queue_frame, tr("Queue")\n\ttab->addTab(metadata_frame, tr("Metadata"))'
            )
            modified = True
        elif 'metadata_frame' in content and 'addTab(metadata_frame' not in content:
            print("      [!] mainwindow.cpp: 'Queue' tab anchor not found — Metadata tab skipped")

    if modified:
        with open(cpp_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return modified


def _patch_rtiframe_h(h_path):
    with open(h_path, encoding='utf-8') as f:
        content = f.read()

    modified = False

    if 'class QCheckBox;' not in content:
        if 'class ZoomOverview;' in content:
            content = content.replace(
                'class ZoomOverview;',
                'class ZoomOverview;\nclass QCheckBox;'
            )
            modified = True
        else:
            print("      [!] rtiframe.h: 'class ZoomOverview;' not found — QCheckBox forward decl skipped")

    if 'rdf_check' not in content:
        for candidate in ('ZoomOverview *zoom_view =  nullptr;', 'ZoomOverview *zoom_view = nullptr;'):
            if candidate in content:
                content = content.replace(
                    candidate,
                    candidate + '\n\tQCheckBox *rdf_check = nullptr;'
                )
                modified = True
                break
        else:
            print("      [!] rtiframe.h: zoom_view member not found — rdf_check member skipped")

    if 'exportRdfSidecar' not in content:
        if 'void updateNPlanes();' in content:
            content = content.replace(
                'void updateNPlanes();',
                'void updateNPlanes();\n\tvoid exportRdfSidecar();'
            )
            modified = True
        else:
            print("      [!] rtiframe.h: updateNPlanes() not found — exportRdfSidecar() skipped")

    if modified:
        with open(h_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return modified


def _patch_rtiframe_cpp(cpp_path):
    with open(cpp_path, encoding='utf-8') as f:
        content = f.read()

    modified = False

    if '#include "rdfexport.h"' not in content:
        if '#include <QFileDialog>' in content:
            content = content.replace(
                '#include <QFileDialog>',
                '#include <QFileDialog>\n#include <QCheckBox>\n#include <QFileInfo>\n#include "rdfexport.h"'
            )
            modified = True
        else:
            print("      [!] rtiframe.cpp: QFileDialog include not found — rdfexport include skipped")

    if 'rdf_check = new QCheckBox' not in content:
        anchor = 'buttons_layout->addWidget(save);'
        if anchor in content:
            replacement = (
                'rdf_check = new QCheckBox("Export RDF/TTL", this);\n'
                '\t\t\t\trdf_check->setChecked(true);\n'
                '\t\t\t\trdf_check->setToolTip("Automatically write a Turtle (.ttl) sidecar alongside the RTI output.");\n'
                '\t\t\t\tbuttons_layout->addWidget(rdf_check);\n'
                '\t\t\t\t' + anchor
            )
            content = content.replace(anchor, replacement, 1)
            modified = True
        else:
            print("      [!] rtiframe.cpp: addWidget(save) not found — checkbox widget skipped")

    if 'exportRdfSidecar' not in content:
        anchor = '\temit processStarted();\n}'
        if anchor in content:
            content = content.replace(
                anchor,
                '\temit processStarted();\n\n'
                '\tif (rdf_check && rdf_check->isChecked()) {\n'
                '\t\tQMetaObject::Connection *conn = new QMetaObject::Connection;\n'
                '\t\t*conn = connect(&ProcessQueue::instance(), qOverload<QJsonObject>(&ProcessQueue::finished),\n'
                '\t\t                this, [this, conn](QJsonObject task) {\n'
                '\t\t\tQObject::disconnect(*conn);\n'
                '\t\t\tdelete conn;\n'
                '\t\t\tif (task.value("status").toInt() != ProcessQueue::STOPPED)\n'
                '\t\t\t\texportRdfSidecar();\n'
                '\t\t});\n'
                '\t}\n}',
                1
            )
            modified = True
        else:
            print("      [!] rtiframe.cpp: emit processStarted() anchor not found — auto-export call skipped")

    if 'void RtiFrame::exportRdfSidecar()' not in content:
        sidecar_impl = (
            '\n\nvoid RtiFrame::exportRdfSidecar() {\n'
            '\tProject &project = qRelightApp->project();\n'
            '\tRdfMetadata meta = RdfExport::readFromProject(project);\n'
            '\n'
            '\tmeta.hasRtiOutput = true;\n'
            '\tmeta.rtiNPlanes   = parameters.nplanes;\n'
            '\tmeta.rtiQuality   = parameters.quality;\n'
            '\tswitch (parameters.basis) {\n'
            '\t\tcase Rti::PTM:      meta.rtiType = "ptm"; break;\n'
            '\t\tcase Rti::HSH:      meta.rtiType = "hsh"; break;\n'
            '\t\tcase Rti::RBF:      meta.rtiType = "rbf"; break;\n'
            '\t\tcase Rti::BILINEAR: meta.rtiType = "bln"; break;\n'
            '\t\tdefault:            meta.rtiType = "rti"; break;\n'
            '\t}\n'
            '\n'
            '\tif (parameters.format == RtiParameters::WEB) {\n'
            '\t\tswitch (parameters.web_layout) {\n'
            '\t\t\tcase RtiParameters::DEEPZOOM: meta.rtiWebLayout = "deepzoom"; break;\n'
            '\t\t\tcase RtiParameters::TARZOOM:  meta.rtiWebLayout = "tarzoom";  break;\n'
            '\t\t\tcase RtiParameters::ITARZOOM: meta.rtiWebLayout = "itarzoom"; break;\n'
            '\t\t\tdefault:                      meta.rtiWebLayout = "plain";    break;\n'
            '\t\t}\n'
            '\t}\n'
            '\n'
            '\tQString p = parameters.path;\n'
            '\tif (p.endsWith(\'/\') || p.endsWith(\'\\\\\')) p.chop(1);\n'
            '\tQFileInfo fi(p);\n'
            '\tQDir    sessionDir = fi.dir();\n'
            '\tQString session    = sessionDir.dirName();\n'
            '\tQDir    figureDir  = sessionDir;\n'
            '\tfigureDir.cdUp();\n'
            '\tQString figure     = figureDir.dirName();\n'
            '\tsession.remove(\'-\');\n'
            '\tQString folderName = fi.fileName();\n'
            '\tQString ttl_name = figure + session + "-" + folderName + ".ttl";\n'
            '\tQString ttl_path = p + "/" + ttl_name;\n'
            '\n'
            '\tQString error;\n'
            '\tif (!RdfExport::write(project, &parameters, meta, ttl_path, error))\n'
            '\t\tQMessageBox::warning(this, "RDF Export", "Could not write TTL:\\n" + error);\n'
            '}\n'
        )
        content += sidecar_impl
        modified = True

    if modified:
        with open(cpp_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return modified


def _rdf_plugin_install(relight_src, logger):
    target_dir   = os.path.join(relight_src, 'relightlab')
    cmake_path   = os.path.join(target_dir, 'CMakeLists.txt')
    mw_h_path    = os.path.join(target_dir, 'mainwindow.h')
    mw_cpp_path  = os.path.join(target_dir, 'mainwindow.cpp')
    rti_h_path   = os.path.join(target_dir, 'rtiframe.h')
    rti_cpp_path = os.path.join(target_dir, 'rtiframe.cpp')
    build_dir    = os.path.join(relight_src, 'build')

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  RDF Plugin Install")
    print(f"  Relight source : {relight_src}")
    print(sep)

    print("\n[1/5] Checking plugin source files...")
    for f in RDF_PLUGIN_FILES:
        src = os.path.join(RDF_PLUGIN_DIR, f)
        if not os.path.exists(src):
            raise RuntimeError(f"Plugin file missing: {src}")
    print(f"      OK — {len(RDF_PLUGIN_FILES)} files ready in rdf-plugin/")
    logger.info("Plugin files: OK")

    print("\n[2/5] Verifying relight source structure...")
    for p, label in [(target_dir, 'relightlab/'), (cmake_path, 'CMakeLists.txt'),
                     (mw_h_path, 'mainwindow.h'), (mw_cpp_path, 'mainwindow.cpp'),
                     (rti_h_path, 'rtiframe.h'),  (rti_cpp_path, 'rtiframe.cpp')]:
        if not os.path.exists(p):
            raise RuntimeError(f"Not found: {label} in {relight_src}")
    print(f"      OK — relightlab/ structure verified")
    logger.info("Relight structure: OK")

    print("\n[3/5] Copying plugin files → relightlab/...")
    for fname in RDF_PLUGIN_FILES:
        src = os.path.join(RDF_PLUGIN_DIR, fname)
        dst = os.path.join(target_dir, fname)
        shutil.copy2(src, dst)
        print(f"      {fname}")
        logger.info(f"Copied: {fname}")

    print("\n[4/5] Patching source files...")
    r1 = _patch_cmake(cmake_path)
    print(f"      CMakeLists.txt — {'patched' if r1 else 'already up-to-date'}")
    r2 = _patch_mainwindow_h(mw_h_path)
    print(f"      mainwindow.h   — {'patched' if r2 else 'already up-to-date'}")
    r3 = _patch_mainwindow_cpp(mw_cpp_path)
    print(f"      mainwindow.cpp — {'patched' if r3 else 'already up-to-date'}")
    r4 = _patch_rtiframe_h(rti_h_path)
    print(f"      rtiframe.h     — {'patched' if r4 else 'already up-to-date'}")
    r5 = _patch_rtiframe_cpp(rti_cpp_path)
    print(f"      rtiframe.cpp   — {'patched' if r5 else 'already up-to-date'}")
    logger.info(f"Patches: cmake={r1} mw_h={r2} mw_cpp={r3} rti_h={r4} rti_cpp={r5}")

    print("\n[5/5] Building relight (cmake + make -j 8)...")
    cmake_cache = os.path.join(build_dir, 'CMakeCache.txt')
    if os.path.exists(cmake_cache):
        os.remove(cmake_cache)
        print("      Removed stale CMakeCache.txt")
        logger.info("Removed stale CMakeCache.txt")
    os.makedirs(build_dir, exist_ok=True)
    logger.info(f"Build dir: {build_dir}")

    cmake_cmd = (
        f"cd '{build_dir}' && "
        f"cmake ../ -DCMAKE_BUILD_TYPE=Release "
        f"-DOpenMP_ROOT=$(brew --prefix libomp) "
        f"-DQt6_DIR=$(brew --prefix qt@6)/lib/cmake/Qt6"
    )
    print("      cmake...")
    proc = subprocess.Popen(["bash", "-c", cmake_cmd],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        line = line.rstrip()
        print(f"      {line}")
        logger.debug(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"cmake failed with exit code {proc.returncode}")
    logger.info("cmake: OK")

    print("      make -j 8...")
    make_cmd = f"cd '{build_dir}' && make -j 8"
    proc = subprocess.Popen(["bash", "-c", make_cmd],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        line = line.rstrip()
        print(f"      {line}")
        logger.debug(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"make failed with exit code {proc.returncode}")
    logger.info("make: OK")

    lab_dir  = os.path.join(build_dir, 'relightlab')
    app_path = next(
        (os.path.join(lab_dir, n) for n in ('relightlab-rdf.app', 'relightlab.app')
         if os.path.exists(os.path.join(lab_dir, n))),
        None
    )
    cli_path = os.path.join(build_dir, 'relight-cli', 'relight-cli')

    print(f"\n{sep}")
    print(f"  Build successful!")
    if app_path:
        print(f"  RelightLab  → {app_path}")
        logger.info(f"RelightLab: {app_path}")
    else:
        print(f"  RelightLab  → (not found in {lab_dir})")
    if os.path.exists(cli_path):
        print(f"  relight-cli → {cli_path}")
        logger.info(f"relight-cli: {cli_path}")
    print(sep)

    return cli_path if os.path.exists(cli_path) else None


def run_rdf_plugin_install():
    console.clear()
    plugin_ok     = all(os.path.exists(os.path.join(RDF_PLUGIN_DIR, f)) for f in RDF_PLUGIN_FILES)
    plugin_status = "OK — 4 files ready" if plugin_ok else "MISSING — copy files to rdf-plugin/"

    console.print()
    console.print(Panel(
        f"  [dim]Patches[/dim]   relightlab/CMakeLists.txt · mainwindow.h · mainwindow.cpp\n"
        f"  [dim]Build[/dim]     cmake → make -j 8\n"
        f"  [dim]Plugin[/dim]    {'[green]' if plugin_ok else '[red]'}{plugin_status}{'[/green]' if plugin_ok else '[/red]'}",
        title="[bold cyan]RDF PLUGIN INSTALL[/bold cyan]  [dim]·  Patch & build RDF export[/dim]",
        border_style="dim",
        padding=(1, 2),
    ))

    if not plugin_ok:
        console.print(f"  [red]Expected: {RDF_PLUGIN_DIR}[/red]")
        _wait_enter()
        return

    relight_raw = _ask("  Relight source path (cloned relight/ folder, Q back): ")
    if relight_raw is None:
        return

    relight_raw = relight_raw.replace('\\ ', ' ').strip().strip("'\"")
    relight_src = os.path.abspath(os.path.expanduser(relight_raw))

    if not os.path.isdir(relight_src):
        console.print(f"  [red][!] Directory not found: {relight_src}[/red]")
        _wait_enter()
        return

    logger, log_path = _make_logger('rdf-plugin', 'install')
    console.print(f"  [dim]Log: {os.path.basename(log_path)}[/dim]")
    console.rule(style="dim")

    try:
        _rdf_plugin_install(relight_src, logger)
    except Exception as e:
        console.print(f"\n  [red][!] Error: {e}[/red]")
        logger.error(str(e))

    _wait_enter()


# ── Logs ───────────────────────────────────────────────────────────────────────

_LOG_MODULES = ['knowledge-graph', 'rdf-plugin']


def _collect_logs():
    entries = []
    for mod in _LOG_MODULES:
        mod_dir = os.path.join(LOGS_DIR, mod)
        if not os.path.isdir(mod_dir):
            continue
        files = sorted(
            glob.glob(os.path.join(mod_dir, '*.log')),
            key=os.path.getmtime, reverse=True
        )
        for f in files:
            size  = os.path.getsize(f)
            s_str = f"{size // 1024}KB" if size >= 1024 else f"{size}B"
            name  = os.path.basename(f)
            label = f"[{mod:<16}]  {name}  ({s_str})"
            entries.append((label, f))
    return entries


def run_log_viewer():
    while True:
        console.clear()
        logs = _collect_logs()
        console.print()
        console.rule("[bold cyan]LOGS[/bold cyan]  [dim]·  Pipeline logs[/dim]")

        if not logs:
            console.print(f"\n  [yellow]No log files found yet.[/yellow]")
            console.print(f"  [dim]Logs are written to: {LOGS_DIR}[/dim]")
            _wait_enter()
            return

        t = Table(show_header=True, box=box.SIMPLE, padding=(0, 1), show_edge=False)
        t.add_column("#",       style="bold cyan",  no_wrap=True, width=4)
        t.add_column("Module",  style="bold white", no_wrap=True, width=20)
        t.add_column("File",    style="white",      no_wrap=True)
        t.add_column("Size",    style="dim",        no_wrap=True, width=8)

        for i, (label, fpath) in enumerate(logs, 1):
            parts   = label.split(']  ', 1)
            mod_str = parts[0].lstrip('[').strip() if parts else ''
            rest    = parts[1] if len(parts) > 1 else label
            fname, _, size_str = rest.rpartition('  (')
            size_str = size_str.rstrip(')')
            t.add_row(f"{i}.", mod_str, fname.strip(), size_str)

        console.print(t)
        console.print("  [dim]Type a number to view, R to refresh, Q to go back.[/dim]")

        val = _ask("  Log: ")
        if val is None:
            return
        if val.upper() == 'R':
            continue

        try:
            idx = int(val) - 1
            if 0 <= idx < len(logs):
                _, log_path = logs[idx]
                try:
                    with open(log_path, encoding='utf-8', errors='replace') as f:
                        content = f.read()
                except Exception as e:
                    content = f"Error reading log: {e}"
                with console.pager(styles=True):
                    console.print(content)
        except ValueError:
            pass


# ── Home screen and main ───────────────────────────────────────────────────────

def draw_home():
    console.clear()
    console.print()
    for line in LOGO:
        console.print(f"[bold cyan]{line}[/bold cyan]")
    console.print()
    console.print(f"  [dim]{TAGLINE}  ·  {VERSION}[/dim]")
    console.print()
    console.rule(style="dim")

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1), show_edge=False)
    t.add_column("Num",  style="bold cyan",  no_wrap=True, width=4)
    t.add_column("Name", style="bold white", no_wrap=True, width=22)
    t.add_column("Desc", style="dim")

    for i, (name, desc) in enumerate(MENU, 1):
        t.add_row(f"{i}.", name, desc)
    t.add_row("Q.", "Quit", "")

    console.print(t)


def main():
    while True:
        draw_home()
        console.print()
        val = _ask("  Select: ")
        if val is None or val.upper() == 'Q':
            break
        if val == '1':
            run_knowledge_graph()
        elif val == '2':
            run_rdf_plugin_install()
        elif val == '3':
            run_log_viewer()


if __name__ == '__main__':
    for d in [DATASETS_DIR, OUTPUTS_DIR, KG_OUTPUTS_DIR,
              os.path.join(LOGS_DIR, 'knowledge-graph'),
              os.path.join(LOGS_DIR, 'rdf-plugin')]:
        os.makedirs(d, exist_ok=True)

    main()
