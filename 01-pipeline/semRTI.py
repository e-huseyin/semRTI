#!/usr/bin/env python3
"""
╔════════════════════════════════════════════════════════════════════════════╗
║ SemRTI — Semantic RTI Knowledge Graph pipeline (standalone)                ║
╠════════════════════════════════════════════════════════════════════════════╣
║ MODULE MAP  —  section index                                               ║
║                                                                            ║
║   1 · Configuration & constants      paths, metadata keys, templates, menu ║
║   2 · File selection & ingestion     which files may enter the graph       ║
║   3 · Logging                        per-run, timestamped log files        ║
║   4 · Terminal UI helpers            input / confirm / wait prompts        ║
║   5 · Dataset tree browser           pick a dataset folder                 ║
║   6 · Metadata & Turtle helpers      enrich-metadata.json -> Turtle        ║
║   7 · Pipeline build steps           EXIF -> SPARQL -> merged .ttl         ║
║   8 · Menu actions — dataset ops     Generate KG / stamp JPGs              ║
║   9 · RelightLab RDF-plugin install  patch & build the C++ plugin          ║
║  10 · Log viewer                     browse pipeline logs                  ║
║  11 · Home screen & entry point      menu loop + first-run scaffolding     ║
╚════════════════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, glob, subprocess, re, shutil, logging, urllib.parse, importlib.util
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# ══════════════════════════════════════════════════════════════════════════
# 1 · CONFIGURATION & CONSTANTS
# Paths, single-source metadata keys, SPARQL templates, banner and menu.
# ══════════════════════════════════════════════════════════════════════════

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
console = Console()

# Project/site metadata (creator, licence, coordinates) is the single source of
# truth in enrich-metadata.json — edit that file, not this script.

DATASETS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '02-datasets'))
OUTPUTS_DIR  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '03-outputs'))
LOGS_DIR     = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '04-logs'))

METADATA_FILE       = os.path.join(SCRIPT_DIR, 'enrich-metadata.json')
METADATA_KEYS = ['author', 'role', 'email', 'orcid', 'affiliation',
                 'license', 'license_url', 'site',
                 'city', 'province', 'country', 'gps_lat', 'gps_lon', 'gps_alt']
SPARQL_ANYTHING_JAR = os.path.join(SCRIPT_DIR, 'sparql-anything.jar')
TEMPLATE_DATASET    = os.path.join(SCRIPT_DIR, 'construct-dataset.sparql')
TEMPLATE_PHOTOS     = os.path.join(SCRIPT_DIR, 'construct-photos.sparql')
TEMPLATE_RTI        = os.path.join(SCRIPT_DIR, 'construct-rti.sparql')
TEMPLATE_PROVENANCE = os.path.join(SCRIPT_DIR, 'construct-provenance.sparql')
ONTOLOGY_TTL        = os.path.join(SCRIPT_DIR, 'rupemagna-rti-ontology.ttl')
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
VERSION = "v1.0.1"

MENU = [
    ("Your metadata → JPG",      "Stamp JPGs from enrich-metadata.json"),
    ("RDF Plugin Install",       "Patch & build RelightLab"),
    ("Generate KG",              "Build final knowledge graph (.ttl)"),
    ("Logs",                     "Browse pipeline logs"),
]

# ══════════════════════════════════════════════════════════════════════════
# 2 · FILE SELECTION & INGESTION POLICY
# Filters shared by the dataset browser and the graph ingestion — real source
# frames and provenance sidecars only; AppleDouble twins and tile pyramids out.
# ══════════════════════════════════════════════════════════════════════════

_TREE_EXCLUDE = {'raw', 'jpg', 'jpg-export', '.ds_store'}


def _tree_excluded(name):
    nl = name.lower()
    return (nl.startswith('.') or
            nl in _TREE_EXCLUDE or
            nl.startswith('jpg-export') or
            nl.startswith('relight-cli-'))


# ── Secure ingestion policy ─────────────────────────────
# Datasets live on external volumes (exFAT/HFS) where macOS scatters AppleDouble
# "._" twins next to every file, and RelightLab writes deep-zoom tile pyramids
# (plane_*_files/) full of 256 px .jpg tiles. Only real source frames — .jpg/.jpeg
# inside a jpg*/jpeg* folder — and RelightLab provenance sidecars
# (*-ptm/-hsh/-rbf.json) may enter the graph. Everything else is ignored.
IGNORE_DIRS = {
    '.git', '.svn', '.hg', '__pycache__', '.DS_Store',
    '.idea', '.vscode', 'node_modules', 'cache', 'tmp', 'temp', 'thumbs',
}
IGNORE_PREFIXES = ('.', '._')
ALLOWED_IMAGE_EXT = {'.jpg', '.jpeg'}
ALLOWED_RTI_SUFFIXES = ('-ptm.json', '-hsh.json', '-rbf.json')


def _iter_source_jpgs(dataset_dir):
    """Yield only real source frames: .jpg/.jpeg files inside a folder whose name
    starts with 'jpg'/'jpeg' (jpg/, jpg-export/, jpg-export-linear/, …), at any
    depth. Hidden dirs, '_files' tile pyramids and IGNORE_DIRS are pruned; '._'
    AppleDouble twins are skipped. Same folder gate the JPG-stamping step uses."""
    for cur, dirs, files in os.walk(dataset_dir):
        dirs[:] = sorted(
            d for d in dirs
            if not d.startswith(IGNORE_PREFIXES)
            and not d.endswith('_files')
            and d.lower() not in IGNORE_DIRS
        )
        if not os.path.basename(cur).lower().startswith(('jpg', 'jpeg')):
            continue
        for f in sorted(files):
            if f.startswith(IGNORE_PREFIXES):
                continue
            if os.path.splitext(f)[1].lower() in ALLOWED_IMAGE_EXT:
                yield os.path.join(cur, f)


def _pick_prov_json(files):
    """Pick the RelightLab provenance sidecar from a session folder's file list:
    the first '*-ptm.json'/'*-hsh.json'/'*-rbf.json' that is not a '._' AppleDouble
    twin. Returns None when absent. Never returns info.json or a '._' binary — the
    latter, picked alphabetically first, is what crashed the JSON reader on the
    external drive (JsonParseException: Illegal character CTRL-CHAR code 5)."""
    return next((fn for fn in sorted(files)
                 if not fn.startswith(IGNORE_PREFIXES)
                 and fn.lower().endswith(ALLOWED_RTI_SUFFIXES)), None)


# ══════════════════════════════════════════════════════════════════════════
# 3 · LOGGING
# Per-run, timestamped log files; one logger per pipeline module.
# ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════
# 4 · TERMINAL UI HELPERS
# Small input / confirm / wait-for-Enter prompts used across the menus.
# ══════════════════════════════════════════════════════════════════════════

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


def _confirm(prompt):
    """Yes/no prompt; True only on an explicit y / yes."""
    val = _ask(prompt)
    return val is not None and val.strip().lower() in ('y', 'yes')


# ══════════════════════════════════════════════════════════════════════════
# 5 · DATASET TREE BROWSER
# Render 02-datasets/ as a numbered tree and resolve the chosen folder.
# ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════
# 6 · METADATA & TURTLE HELPERS
# enrich-metadata.json -> validated Turtle for the project agent, site and
# GeoSPARQL geometry. Structure lives here; values come from the single source.
# ══════════════════════════════════════════════════════════════════════════

def _load_metadata():
    """Load project/site metadata from enrich-metadata.json — the single source
    of truth. Returns the config dict, or None if the file is missing/invalid."""
    if not os.path.exists(METADATA_FILE):
        return None
    try:
        with open(METADATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _to_file_uri(path):
    abspath = os.path.abspath(path)
    if os.name == 'nt':
        # SPARQL Anything's triplifier (commons-io FilenameUtils) rejects any
        # ':' in a location string as a possible NTFS ADS separator, which
        # breaks ordinary "C:\..." absolute paths. Route through the local
        # admin share (\\localhost\c$\...) instead — same file, no colon.
        drive, rest = os.path.splitdrive(abspath)
        abspath = '//localhost/' + drive.rstrip(':').lower() + '$' + rest
        abspath = abspath.replace('\\', '/')
        return 'file://' + urllib.parse.quote(abspath, safe='/')
    return 'file://' + urllib.parse.quote(abspath, safe='/:')


def _ttl_literal(s):
    """Escape a value for use inside a Turtle quoted literal (incl. control chars)."""
    return (str(s).replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'))


def _ttl_number(value):
    """Return value unchanged if it is a real number, else None.
    Keeps a malformed geo coordinate from breaking the whole graph (validated,
    original formatting preserved)."""
    try:
        float(value)
    except (TypeError, ValueError):
        return None
    return str(value).strip()


_ORCID_RE = re.compile(r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$')


def _orcid_iri(value):
    """Return a valid absolute ORCID IRI, or None if value is not a usable ORCID.
    Accepts a full http(s) URL or a bare 16-digit ORCID (normalised to the URL form)."""
    if not value:
        return None
    v = str(value).strip()
    if v.startswith(('http://', 'https://')) and ' ' not in v:
        return v
    if _ORCID_RE.match(v):
        return 'https://orcid.org/' + v
    return None


def _metadata_ttl(meta):
    """Turtle for the project agent and site whose VALUES come from
    enrich-metadata.json. Only non-blank fields are emitted, so a missing value
    simply produces no triple (no broken literal). The structure (which property,
    which subject) lives here; the values come from the single source. Must be
    parsed together with shared.ttl so the prefixes resolve."""
    agent = []
    if meta.get('author'):      agent.append(f'    foaf:name "{_ttl_literal(meta["author"])}"')
    if meta.get('email'):       agent.append(f'    foaf:mbox <mailto:{meta["email"]}>')
    orcid_iri = _orcid_iri(meta.get('orcid'))
    if orcid_iri:               agent.append(f'    schema:identifier <{orcid_iri}>')
    if meta.get('affiliation'): agent.append(f'    schema:affiliation "{_ttl_literal(meta["affiliation"])}"')
    if meta.get('role'):        agent.append(f'    schema:jobTitle "{_ttl_literal(meta["role"])}"')

    site = []
    lat = _ttl_number(meta.get('gps_lat'))
    lon = _ttl_number(meta.get('gps_lon'))
    alt = _ttl_number(meta.get('gps_alt'))
    if lat is not None:  site.append(f'    geo:lat   {lat}')
    if lon is not None:  site.append(f'    geo:long  {lon}')
    if alt is not None:  site.append(f'    geo:alt   {alt}')
    # GeoSPARQL geometry link — emitted only when both coordinates are present, so the
    # WKT below is derived from the same lat/long and therefore agrees with the WGS84 point.
    if lat is not None and lon is not None:
        site.append('    geosparql:hasGeometry rpm-rti:geom-rupe-magna')
    if meta.get('city'):     site.append(f'    schema:addressLocality "{_ttl_literal(meta["city"])}"')
    if meta.get('province'): site.append(f'    schema:addressRegion   "{_ttl_literal(meta["province"])}"')
    if meta.get('country'):  site.append(f'    schema:addressCountry  "{_ttl_literal(meta["country"])}"')

    # license_url is referenced by dct:license/dct:rights all over the KG
    # (via LICENSE_URL_PLACEHOLDER) but was never itself typed, so every
    # sh:class check on those values failed SHACL. Typed once here, from the
    # single source, rather than per-triple in each construct-*.sparql.
    license_url = meta.get('license_url')
    is_license_iri = (isinstance(license_url, str)
                       and license_url.startswith(('http://', 'https://'))
                       and ' ' not in license_url)

    blocks = []
    if agent:
        blocks.append("rpm-rti:agent-huseyin-erdogan\n" + " ;\n".join(agent) + " .")
    if site:
        blocks.append("rpm-rti:site-rupe-magna\n" + " ;\n".join(site) + " .")
    if is_license_iri:
        blocks.append(f'<{license_url}>\n    a dct:LicenseDocument .')
    # GeoSPARQL geometry individual for the site (WKT order is POINT(long lat)). Named node
    # (rpm-rti:geom-) rather than a blank node, to keep the ABox clean. Its prefixes (rdf/owl/
    # geosparql/rpm-rti) are declared in shared.ttl and resolve once this block is merged with
    # shared_text and parsed as a single graph.
    if lat is not None and lon is not None:
        blocks.append(
            "rpm-rti:geom-rupe-magna\n"
            "    rdf:type owl:NamedIndividual, geosparql:Geometry ;\n"
            f'    geosparql:asWKT "POINT({lon} {lat})"^^geosparql:wktLiteral .'
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


# ══════════════════════════════════════════════════════════════════════════
# 7 · PIPELINE BUILD STEPS
# The build engine: JPG stamping · EXIF export · SPARQL Anything CONSTRUCTs
# (dataset / photos / RTI provenance) · merge into one final .ttl.
# ══════════════════════════════════════════════════════════════════════════

def _kg_step1_metadata(dataset_dir, site_name, meta, logger):
    author      = meta.get('author', '')
    role        = meta.get('role', '')
    email       = meta.get('email', '')
    orcid       = meta.get('orcid', '')
    affiliation = meta.get('affiliation', '')
    license_str = meta.get('license', 'Licensed under CC BY 4.0')
    license_url = meta.get('license_url', 'https://creativecommons.org/licenses/by/4.0/')
    city        = meta.get('city', '')
    province    = meta.get('province', '')
    country     = meta.get('country', '')
    gps_lat     = meta.get('gps_lat', '')
    gps_lon     = meta.get('gps_lon', '')
    gps_alt     = meta.get('gps_alt', '')

    total = 0

    # Stamp only the photographer's input images: any folder whose name starts
    # with "jpg" or "jpeg" (jpg-export, jpeg-exports, "jpg raw", …), at any depth.
    # RelightLab output folders (ptm, hsh, rbf, …) never match by name, and their
    # deepzoom tile pyramids (*_files) are pruned, so their images are untouched.
    for cur, dirs, files in os.walk(dataset_dir):
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith('.') and not d.endswith('_files'))

        if not os.path.basename(cur).lower().startswith(('jpg', 'jpeg')):
            continue
        imgs = [
            f for f in files
            if not f.startswith('._')
            and f.lower().endswith(('.jpg', '.jpeg'))
        ]
        if not imgs:
            continue

        # Build the RDF label from the standard dataset layout:
        # <Site>/<Object>/<RTI session>/<jpg-folder>
        # → <Site> - [<Object>] - [<RTI session>]
        rel = os.path.relpath(cur, DATASETS_DIR)
        parts = rel.split(os.sep)

        rti_name = parts[-2] if len(parts) >= 2 else os.path.basename(cur)
        f_name = parts[-3] if len(parts) >= 3 else ""

        label = (
            f"{site_name} - [{f_name}] - [{rti_name}]"
            if f_name else f"{site_name} - [{rti_name}]"
        )

        cmd = ['exiftool', '-overwrite_original', '-P', '-m', '-q',
               '-i', '.*', '-ext', 'jpg', '-ext', 'jpeg',
               f'-Title={label}',
               f'-XMP-dc:title={label}',
               f'-Description={label}',
               f'-XMP-dc:description={label}',
               f'-Caption-Abstract={label}',
               f'-Keywords=RTI, {site_name}, FAIR data, ArCo, {label}',
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
               cur]

        if gps_lat:
            cmd += [f'-GPSLatitude={gps_lat}', '-GPSLatitudeRef=N']
        if gps_lon:
            cmd += [f'-GPSLongitude={gps_lon}', '-GPSLongitudeRef=E']
        if gps_alt:
            cmd += [f'-GPSAltitude={gps_alt}', '-GPSAltitudeRef=0']

        result = subprocess.run(cmd, capture_output=True, text=True)
        n = len(imgs)
        if result.returncode != 0:
            # exiftool failed here — do not report unstamped files as done.
            logger.error(f"exiftool failed for {cur} (rc={result.returncode}): "
                         f"{result.stderr.strip()}")
            print(f"           {label} — FAILED ({n} files skipped)")
            continue

        total += n
        print(f"           {label} — {n} files")
        logger.info(f"Metadata written: {label}  ({n} files)")

    return total


def _kg_step2_exif_export(dataset_dir, exif_json, logger):
    # Feed exiftool an explicit allow-listed file list instead of '-r' over the
    # whole volume. The old blanket recursion pulled in the deep-zoom tile
    # pyramids and every '._' AppleDouble twin — 130k+ records where < 1 % were
    # real frames — bloating the run and the EXIF JSON. Now only real source
    # frames are read.
    sources = list(_iter_source_jpgs(dataset_dir))
    if not sources:
        logger.warning(f"No source JPGs under jpg*/jpeg* folders in {dataset_dir}")
        with open(exif_json, 'w', encoding='utf-8') as f:
            f.write('[]')
        return 0

    argfile = exif_json + '.filelist'
    with open(argfile, 'w', encoding='utf-8') as af:
        af.write('\n'.join(sources) + '\n')

    cmd = ['exiftool', '-j',
           '-SourceFile', '-FileName', '-CreateDate', '-FileSize',
           '-ImageWidth', '-ImageHeight',
           '-ISO', '-FNumber', '-ExposureTime', '-FocalLength',
           '-@', argfile]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        try:
            os.remove(argfile)
        except OSError:
            pass

    if result.returncode != 0:
        logger.error(f"exiftool export failed: {result.stderr.strip()}")
        return 0

    # Validate BEFORE writing: a truncated/garbled exiftool output must never reach
    # disk, otherwise the next SPARQL step would silently consume corrupt EXIF.
    try:
        records = json.loads(result.stdout)
    except Exception as e:
        logger.error(f"exiftool returned invalid JSON — writing empty set instead: {e}")
        with open(exif_json, 'w', encoding='utf-8') as f:
            f.write('[]')
        return 0

    with open(exif_json, 'w', encoding='utf-8') as f:
        f.write(result.stdout)
    count = len(records)
    n_folders = len({os.path.dirname(s) for s in sources})
    logger.info(f"EXIF export: {count} records from {n_folders} source "
                f"folder(s) → {exif_json}")
    return count


def _run_construct(template_path, replacements, out_path, logger):
    """Render a SPARQL Anything CONSTRUCT template (substituting the given
    token→value pairs), run it, and write Turtle to out_path. Returns True on
    success. The temporary query file is always cleaned up.

    This is the single SPARQL driver shared by the dataset, photo and RTI builders."""
    if not os.path.exists(template_path):
        logger.error(f"Template not found: {template_path}")
        return False

    with open(template_path, encoding='utf-8') as f:
        query = f.read()
    for token, value in replacements.items():
        query = query.replace(token, value)

    tmp = os.path.join(SCRIPT_DIR, '_tmp-' + os.path.basename(template_path))
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(query)

    try:
        result = subprocess.run(
            # -Dfile.encoding/-Dsun.jnu.encoding/-Dnative.encoding: on Java <18
            # these default to the platform's ANSI codepage (Cp1252 on
            # Windows), so the JVM reads this UTF-8 query file's non-ASCII
            # literals (accented names, em dashes) as Cp1252 and re-encodes
            # the already-wrong string as UTF-8 on the way out, i.e. mojibake.
            ['java', '-Dfile.encoding=UTF-8', '-Dsun.jnu.encoding=UTF-8',
             '-Dnative.encoding=UTF-8', '-jar', SPARQL_ANYTHING_JAR,
             '-q', tmp, '-o', out_path],
            capture_output=True, text=True
        )
    finally:
        # Remove the temp query even if the run is interrupted, so no stray
        # _tmp-*.sparql is left in the watched SCRIPT_DIR.
        try:
            os.remove(tmp)
        except OSError:
            pass

    if result.returncode != 0:
        logger.error(f"SPARQL Anything failed "
                     f"({os.path.basename(template_path)}):\n{result.stderr.strip()}")
        return False
    return True


def _kg_step3_section_c(exif_json, output_c, extra, logger):
    if not os.path.exists(KG_DATASET_CSV):
        logger.error(f"dataset-config.csv not found: {KG_DATASET_CSV}"); return False

    ok = _run_construct(TEMPLATE_DATASET, {
        'EXIF_LOCATION_PLACEHOLDER': _to_file_uri(exif_json),
        'CSV_LOCATION_PLACEHOLDER':  _to_file_uri(KG_DATASET_CSV),
        **extra,
    }, output_c, logger)
    if ok:
        logger.info(f"Dataset triples → {output_c}")
    return ok


def _kg_step4_section_d(exif_json, output_d, extra, logger):
    ok = _run_construct(TEMPLATE_PHOTOS, {
        'EXIF_LOCATION_PLACEHOLDER': _to_file_uri(exif_json),
        **extra,
    }, output_d, logger)
    if ok:
        logger.info(f"Photo triples → {output_d}")
    return ok


def _kg_section_e(datasets_dir, extra, logger):
    """Build all RTI provenance triples from the per-dataset provenance JSONs via
    construct-rti.sparql (SPARQL Anything). Returns (rdflib.Graph, dataset_count).
    A provenance JSON is any *.json sitting next to an info.json (not info.json
    itself) — i.e. RelightLab's F01RTI08-ptm.json sidecar."""
    import rdflib
    g = rdflib.Graph()
    if not os.path.exists(TEMPLATE_RTI):
        logger.error(f"Template not found: {TEMPLATE_RTI}")
        return g, 0

    count = 0
    tmp_o = os.path.join(SCRIPT_DIR, '_tmp-rti-out.ttl')
    tmp_p = os.path.join(SCRIPT_DIR, '_tmp-provenance-out.ttl')
    for root, dirs, files in os.walk(datasets_dir):
        if 'info.json' not in files:
            continue
        prov = _pick_prov_json(files)
        if not prov:
            continue
        prov_path = os.path.join(root, prov)
        info_path = os.path.join(root, 'info.json')

        ok = _run_construct(TEMPLATE_RTI, {
            'PROV_LOCATION_PLACEHOLDER': _to_file_uri(prov_path),
            'INFO_LOCATION_PLACEHOLDER': _to_file_uri(info_path),
            **extra,
        }, tmp_o, logger)
        if ok:
            try:
                g.parse(tmp_o, format='turtle')
                count += 1
                disp = os.path.relpath(root, datasets_dir)
                print(f"           {disp}")
                logger.info(f"RTI provenance: {disp} ({prov})")
            except Exception as e:
                logger.warning(f"RTI provenance parse failed for {prov_path}: {e}")
        else:
            disp = os.path.relpath(root, datasets_dir)
            print(f"           [FAILED] {disp}")
            logger.warning(f"RTI provenance FAILED for {disp} ({prov}) — see SPARQL error above")
        try:
            os.remove(tmp_o)
        except Exception:
            pass

        # CRMdig process chain (RAWDevelopment/RTIFitting activities, D9 data
        # objects) — same provenance JSON, no info.json needed. Failures here
        # are logged but don't fail the dataset: the core RTI triples above
        # already succeeded.
        if os.path.exists(TEMPLATE_PROVENANCE):
            ok_p = _run_construct(TEMPLATE_PROVENANCE, {
                'PROV_LOCATION_PLACEHOLDER': _to_file_uri(prov_path),
                **extra,
            }, tmp_p, logger)
            if ok_p:
                try:
                    g.parse(tmp_p, format='turtle')
                    logger.info(f"Process-chain provenance: {os.path.relpath(root, datasets_dir)} ({prov})")
                except Exception as e:
                    logger.warning(f"Process-chain provenance parse failed for {prov_path}: {e}")
            else:
                logger.warning(f"Process-chain provenance FAILED for {os.path.relpath(root, datasets_dir)} ({prov})")
            try:
                os.remove(tmp_p)
            except Exception:
                pass
    return g, count


# Logical categories for the human-readable output, in file order. The written
# graph is identical to a flat serialisation — only the subject order and the
# added `#` section banners differ. Every triple is routed to exactly one bucket
# (see _CATEGORY_PRIORITY); anything unmatched lands in OTHER, so a new ontology
# class never drops a triple — it just shows up under OTHER until mapped here.
_CAT_ORDER = [
    "PROJECT", "SITE & FIGURES", "PEOPLE", "EQUIPMENT", "SURVEYS",
    "OBSERVATIONS", "MEASUREMENTS", "MEDIA & RESULTS", "DATASETS",
    "VOCABULARY", "OTHER",
]
_CAT_CLASSES = {
    "PROJECT":         "chs:CulturalHeritageProject",
    "SITE & FIGURES":  "arco:ArchaeologicalProperty · geosparql:Geometry",
    "PEOPLE":          "core:Agent · foaf:Person · core:AgentRole",
    "EQUIPMENT":       "chs:Hardware · chs:EquipmentConfiguration",
    "SURVEYS":         "chs:CulturalHeritageSurvey",
    "OBSERVATIONS":    "chs:ObservationCollection · chs:Observation",
    "MEASUREMENTS":    "a-dd:MeasurementCollection · a-dd:Measurement",
    "MEDIA & RESULTS": "a-cd:PhotographicDocumentation · chs:Result",
    "DATASETS":        "dcat:DatasetSeries · dcat:Dataset · dcat:Distribution",
    "VOCABULARY":      "a-dd:MeasurementType · muapit:MeasurementUnit · chs:Method",
    "OTHER":           "any individual not matched above",
}
_CAT_NS = {
    "chs":  "http://www.ontologydesignpatterns.org/cp/owl/culturalheritagesurvey.owl#",
    "arco": "https://w3id.org/arco/ontology/arco/",
    "core": "https://w3id.org/arco/ontology/core/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "add":  "https://w3id.org/arco/ontology/denotative-description/",
    "acd":  "https://w3id.org/arco/ontology/context-description/",
    "mua":  "http://www.ontologydesignpatterns.org/ont/dul/muapit.owl#",
    "geos": "http://www.opengis.net/ont/geosparql#",
}
# First matching rdf:type wins, so a subject with several types (e.g. a
# dcat:Distribution that is also a chs:Result) lands in exactly one category.
_CATEGORY_PRIORITY = [
    (_CAT_NS["dcat"] + "Distribution",              "DATASETS"),
    (_CAT_NS["dcat"] + "DatasetSeries",             "DATASETS"),
    (_CAT_NS["dcat"] + "Dataset",                   "DATASETS"),
    (_CAT_NS["acd"]  + "PhotographicDocumentation", "MEDIA & RESULTS"),
    (_CAT_NS["chs"]  + "Result",                    "MEDIA & RESULTS"),
    (_CAT_NS["chs"]  + "CulturalHeritageProject",   "PROJECT"),
    (_CAT_NS["geos"] + "Geometry",                  "SITE & FIGURES"),
    (_CAT_NS["arco"] + "ArchaeologicalProperty",    "SITE & FIGURES"),
    (_CAT_NS["core"] + "AgentRole",                 "PEOPLE"),
    (_CAT_NS["foaf"] + "Person",                    "PEOPLE"),
    (_CAT_NS["core"] + "Agent",                     "PEOPLE"),
    (_CAT_NS["chs"]  + "EquipmentConfiguration",    "EQUIPMENT"),
    (_CAT_NS["chs"]  + "Hardware",                  "EQUIPMENT"),
    (_CAT_NS["chs"]  + "CulturalHeritageSurvey",    "SURVEYS"),
    (_CAT_NS["chs"]  + "ObservationCollection",     "OBSERVATIONS"),
    (_CAT_NS["chs"]  + "Observation",               "OBSERVATIONS"),
    (_CAT_NS["add"]  + "MeasurementCollection",     "MEASUREMENTS"),
    (_CAT_NS["add"]  + "Measurement",               "MEASUREMENTS"),
    (_CAT_NS["add"]  + "MeasurementType",           "VOCABULARY"),
    (_CAT_NS["mua"]  + "MeasurementUnit",           "VOCABULARY"),
    (_CAT_NS["chs"]  + "Method",                    "VOCABULARY"),
]


def _serialize_categorised(g, out_path):
    """Write g to out_path as Turtle, grouped into logical categories with a
    single prefix header and `# ===` section banners. Works on the RDF graph,
    never on the serialised text. The triples are identical to a flat
    serialisation — proven here by sum-of-parts == len(g) — only the subject
    order and the added comment banners differ; nothing is deleted."""
    import rdflib
    from rdflib import RDF

    def _ttl(x):
        return x.decode("utf-8") if isinstance(x, bytes) else x

    # 1 · subject -> category index (first matching rdf:type wins, else OTHER).
    types = {}
    for s, _, o in g.triples((None, RDF.type, None)):
        types.setdefault(s, set()).add(str(o))
    index = {}
    for s, tset in types.items():
        chosen = "OTHER"
        for tiri, cat in _CATEGORY_PRIORITY:
            if tiri in tset:
                chosen = cat
                break
        index[s] = chosen

    # 2 · one single pass: route every triple into its category bucket graph.
    buckets = {c: rdflib.Graph() for c in _CAT_ORDER}
    for b in buckets.values():
        for pfx, ns in g.namespaces():
            b.bind(pfx, ns, replace=True)
    for s, p, o in g:
        buckets[index.get(s, "OTHER")].add((s, p, o))

    # Completeness + disjointness guard: nothing dropped, nothing duplicated.
    assert sum(len(b) for b in buckets.values()) == len(g), \
        "categorised writer lost or duplicated triples"

    # 3 · one prefix header for the whole file (from rdflib's own output).
    prefix_block = "\n".join(
        ln for ln in _ttl(g.serialize(format="turtle")).splitlines()
        if ln.startswith(("@prefix", "@base"))
    )

    def _body(bucket):
        return "\n".join(
            ln for ln in _ttl(bucket.serialize(format="turtle")).splitlines()
            if not ln.startswith(("@prefix", "@base"))
        ).strip("\n")

    bar = "# " + "═" * 74
    parts = [
        bar,
        "# RUPE MAGNA RTI KNOWLEDGE GRAPH",
        f"# {len(g)} triples · grouped into logical sections for readability.",
        "# Identical graph to a flat serialisation — only order + banners differ.",
        bar, "", prefix_block, "",
    ]
    for cat in _CAT_ORDER:
        b = buckets[cat]
        if len(b) == 0:
            continue
        parts += [bar, f"# {cat}",
                  f"#   {_CAT_CLASSES[cat]}  ·  {len(b)} triples",
                  bar, "", _body(b), ""]

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts).rstrip("\n") + "\n")


def _kg_apply_reasoning(g, logger, ontology_path=ONTOLOGY_TTL):
    """Materialise OWL-RL/RDFS entailments (subclass/subproperty closure,
    owl:inverseOf, owl:propertyChainAxiom, …) over the merged KG graph `g`
    against the ontology's TBox, in place. Optional pipeline step — off by
    default because it changes triple count/shape and adds build time.

    Only NEW facts about individuals already present in `g` are kept: the
    ontology at `ontology_path` (defaults to ONTOLOGY_TTL, but the user can
    point this at any TTL from the menu) is reasoned over alongside the KG in
    a working copy, then any entailed triple whose subject isn't already a
    subject in `g` is discarded (that's a pure TBox-internal entailment —
    e.g. transitive subClassOf between two ontology classes — not a fact
    about one of this project's individuals, so it has no place in a
    per-project ABox file). Trivial OWL-RL boilerplate (every individual is
    tautologically owl:Thing and owl:sameAs itself) is dropped too — it
    carries no information and would otherwise be ~35% of the output.
    Returns the number of triples added to `g`."""
    import rdflib
    from owlrl import DeductiveClosure, OWLRL_Semantics
    from rdflib.namespace import RDF, OWL

    if not os.path.exists(ontology_path):
        logger.warning(f"Reasoning skipped: ontology not found ({ontology_path})")
        return 0

    subjects_in_g = set(g.subjects())

    working = rdflib.Graph()
    for t in g:
        working.add(t)
    working.parse(ontology_path, format='turtle')
    before = len(working)

    DeductiveClosure(OWLRL_Semantics).expand(working)
    logger.info(f"Reasoning: {before} -> {len(working)} triples in the working (KG+ontology) graph")

    added = 0
    for t in working:
        if t in g:
            continue
        s, p, o = t
        if s not in subjects_in_g:
            continue
        if p == RDF.type and o == OWL.Thing:
            continue
        if p == OWL.sameAs and s == o:
            continue
        g.add(t)
        added += 1
    return added


def _kg_build_final(dataset_dir, site_name, meta, logger, apply_reasoning=False,
                     ontology_path=ONTOLOGY_TTL):
    """Build a single final Knowledge Graph TTL: EXIF → dataset + photo triples
    (SPARQL Anything) + RTI provenance (provenance JSON) + shared.ttl, merged in
    memory with rdflib and written once. No intermediate triple files; no JPG
    stamping (that is a separate menu item). If apply_reasoning is True, an
    extra OWL-RL closure step runs after the merge (see _kg_apply_reasoning),
    reasoning over `ontology_path` (defaults to ONTOLOGY_TTL)."""
    import rdflib
    safe_site = re.sub(r'[^\w\-]', '-', site_name).lower().strip('-')
    os.makedirs(KG_OUTPUTS_DIR, exist_ok=True)

    exif_json = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-exif.json')
    final_ttl = os.path.join(KG_OUTPUTS_DIR, f'{safe_site}-knowledge-graph.ttl')
    tmp_c     = os.path.join(SCRIPT_DIR, '_tmp-section-c.ttl')
    tmp_d     = os.path.join(SCRIPT_DIR, '_tmp-section-d.ttl')
    total_steps = 5 if apply_reasoning else 4

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  RTI Knowledge Graph — {site_name}")
    print(f"  Dataset : {dataset_dir}")
    print(sep)

    print(f"\n[1/{total_steps}] Exporting EXIF to JSON...")
    logger.info("=== EXIF export ===")
    n = _kg_step2_exif_export(dataset_dir, exif_json, logger)
    print(f"      → {n} records")

    print(f"\n[2/{total_steps}] Generating dataset + photo triples (SPARQL Anything)...")
    logger.info("=== Dataset + photo triples ===")
    # Personal-metadata injection: the licence IRI is the only value carried by
    # the SPARQL templates; everything else (agent/site values) is added to the
    # static graph below. Sourced from enrich-metadata.json.
    extra = {'LICENSE_URL_PLACEHOLDER': meta.get('license_url', '')}
    ok_c = _kg_step3_section_c(exif_json, tmp_c, extra, logger)
    ok_d = _kg_step4_section_d(exif_json, tmp_d, extra, logger)
    print(f"      → C: {'OK' if ok_c else 'FAILED'}   D: {'OK' if ok_d else 'FAILED'}")
    if not (ok_c and ok_d):
        # A partial graph (missing dataset/photo triples) must not be reported as success.
        failed = [n for n, ok in (('dataset (C)', ok_c), ('photo (D)', ok_d)) if not ok]
        for t in (tmp_c, tmp_d):
            try:
                os.remove(t)
            except OSError:
                pass
        raise RuntimeError(f"knowledge-graph build failed: {', '.join(failed)} produced no triples")

    print(f"\n[3/{total_steps}] Mapping RTI provenance...")
    logger.info("=== RTI provenance ===")
    g_e, e_count = _kg_section_e(dataset_dir, extra, logger)
    print(f"      → {e_count} RTI dataset(s)")

    print(f"\n[4/{total_steps}] Merging into single final graph...")
    logger.info("=== Merge ===")
    g = rdflib.Graph()
    if os.path.exists(KG_SHARED_TTL):
        with open(KG_SHARED_TTL, encoding='utf-8') as f:
            shared_text = f.read()
        shared_text = shared_text.replace('LICENSE_URL_PLACEHOLDER',
                                          meta.get('license_url', ''))
        shared_text += "\n" + _metadata_ttl(meta)
        g.parse(data=shared_text, format='turtle')
    for part in (tmp_c, tmp_d):
        if os.path.exists(part):
            try:
                g.parse(part, format='turtle')
            except Exception as ex:
                logger.warning(f"merge parse failed for {part}: {ex}")
    g += g_e
    print(f"      → {len(g)} triples")

    if apply_reasoning:
        print(f"\n[5/{total_steps}] Applying OWL-RL reasoning...")
        logger.info("=== Reasoning ===")
        added = _kg_apply_reasoning(g, logger, ontology_path=ontology_path)
        print(f"      → +{added} entailed triples")

    _serialize_categorised(g, final_ttl)
    for t in (tmp_c, tmp_d):
        try:
            os.remove(t)
        except Exception:
            pass

    print(f"\n{sep}")
    print(f"  Done → {final_ttl}")
    print(f"{sep}\n")
    logger.info(f"=== Build complete: {len(g)} triples → {final_ttl} ===")
    return len(g)


# ══════════════════════════════════════════════════════════════════════════
# 8 · MENU ACTIONS — DATASET OPERATIONS
# Front-end flows: pick a dataset, then Generate Knowledge Graph or stamp JPGs.
# ══════════════════════════════════════════════════════════════════════════

def _choose_dataset(title, subtitle):
    """Shared front-end for the dataset operations: clear the screen, load the
    project metadata, let the user pick a dataset folder, and resolve its path.
    Returns (meta, dataset_dir, site_name), or None if the user cancels or
    enrich-metadata.json is missing/invalid."""
    console.clear()
    meta = _load_metadata()
    if meta is None:
        console.print(f"\n  [red][!] {os.path.basename(METADATA_FILE)} not found or invalid — "
                      f"create it first.[/red]")
        _wait_enter()
        return None

    missing = [k for k in METADATA_KEYS if k not in meta]
    if missing:
        console.print(f"  [yellow][!] enrich-metadata.json missing field(s): "
                      f"{', '.join(missing)} — they will be left blank.[/yellow]")

    dataset_raw = _dataset_picker(title, subtitle)
    if not dataset_raw:
        return None

    dataset_raw = dataset_raw.replace('\\ ', ' ')
    if os.path.isabs(dataset_raw):
        dataset_dir = os.path.normpath(dataset_raw)
    else:
        dataset_dir = os.path.join(DATASETS_DIR, dataset_raw)

    return meta, dataset_dir, meta.get('site', 'dataset')


def run_knowledge_graph():
    chosen = _choose_dataset("GENERATE KNOWLEDGE GRAPH",
                             "·  EXIF → RDF/Turtle  ·  dataset · photos · RTI")
    if not chosen:
        return
    meta, dataset_dir, site_name = chosen

    missing = []
    for dep in ['exiftool', 'java']:
        if shutil.which(dep) is None:
            missing.append(dep)
    if not os.path.exists(SPARQL_ANYTHING_JAR):
        missing.append('sparql-anything.jar')
    if not os.path.isdir(dataset_dir):
        missing.append(f'dataset not found: {dataset_dir}')

    if missing:
        console.print()
        console.rule("[bold red]GENERATE KNOWLEDGE GRAPH  ·  Prerequisites missing[/bold red]")
        for m in missing:
            console.print(f"  [red][!][/red]  {m}")
        _wait_enter()
        return

    # Scan for RTI datasets: folders with info.json + a provenance JSON sidecar
    prov_count = 0
    for root, dirs, files in os.walk(dataset_dir):
        if 'info.json' in files and _pick_prov_json(files):
            prov_count += 1

    console.clear()
    console.print()
    console.rule(f"[bold cyan]GENERATE KNOWLEDGE GRAPH[/bold cyan]  [dim]·  {site_name}[/dim]")
    console.print(f"  [dim]Dataset : {dataset_dir}[/dim]")
    console.print()
    console.print(f"  Found [bold]{prov_count}[/bold] RTI dataset(s) with a provenance JSON.")
    console.print()
    if prov_count == 0:
        console.print("  [yellow]No provenance JSON found — process the RTIs in RelightLab first.[/yellow]")
        _wait_enter()
        return

    if not _confirm("  Build the final knowledge graph from these? (y/N): "):
        return

    apply_reasoning = False
    ontology_path = ONTOLOGY_TTL
    if importlib.util.find_spec('owlrl') is not None:
        apply_reasoning = _confirm(
            "  Apply OWL-RL reasoning to materialise subclass/subproperty "
            "inferences (e.g. chs:CulturalProperty, crm:P2_has_type)? (y/N): ")
        if apply_reasoning:
            ontology_path = _ask(
                f"  Ontology TTL to reason over [{os.path.basename(ONTOLOGY_TTL)}]: ",
                default=ONTOLOGY_TTL) or ONTOLOGY_TTL
            if not os.path.isabs(ontology_path):
                ontology_path = os.path.join(SCRIPT_DIR, ontology_path)
            if not os.path.exists(ontology_path):
                console.print(f"  [yellow]Ontology file not found ({ontology_path}) — "
                               "reasoning will be skipped.[/yellow]")
    else:
        console.print("  [dim]owlrl not installed — skipping optional reasoning step "
                       "(pip install owlrl to enable).[/dim]")

    logger, log_path = _make_logger('knowledge-graph', site_name)
    logger.info(f"Dataset: {dataset_dir}")
    logger.info(f"Site:    {site_name}")

    console.clear()
    console.print()
    console.rule(f"[bold cyan]GENERATE KNOWLEDGE GRAPH[/bold cyan]  [dim]·  {site_name}[/dim]")
    console.print(f"  [dim]Dataset : {dataset_dir}[/dim]")
    console.print(f"  [dim]Log     : {os.path.basename(log_path)}[/dim]")
    console.rule(style="dim")

    try:
        _kg_build_final(dataset_dir, site_name, meta, logger, apply_reasoning=apply_reasoning,
                         ontology_path=ontology_path)
    except Exception as e:
        console.print(f"\n  [red][!] Error: {e}[/red]")
        logger.error(str(e), exc_info=True)

    _wait_enter()


def run_jpg_metadata():
    """Standalone: stamp creator & licence (from enrich-metadata.json) into the
    JPGs via exiftool. Separate from graph building — for archiving / sharing."""
    chosen = _choose_dataset("YOUR METADATA → JPG",
                             "·  Stamp JPGs from enrich-metadata.json")
    if not chosen:
        return
    meta, dataset_dir, site_name = chosen

    if shutil.which('exiftool') is None:
        console.print("\n  [red][!] exiftool not found[/red]")
        _wait_enter()
        return
    if not os.path.isdir(dataset_dir):
        console.print(f"\n  [red][!] dataset not found: {dataset_dir}[/red]")
        _wait_enter()
        return

    console.clear()
    console.print()
    console.rule(f"[bold cyan]YOUR METADATA → JPG[/bold cyan]  [dim]·  {site_name}[/dim]")
    console.print(f"  [dim]Dataset : {dataset_dir}[/dim]")
    console.print()
    console.print("  This writes the enrich-metadata.json fields into the JPG files themselves.")
    console.print()
    if not _confirm("  Stamp metadata into JPGs? (y/N): "):
        return

    logger, _ = _make_logger('jpg-metadata', site_name)
    logger.info(f"JPG metadata stamping — {dataset_dir}")
    try:
        total = _kg_step1_metadata(dataset_dir, site_name, meta, logger)
        if total > 0:
            console.print(f"\n  [green]✓ {total} JPG file(s) updated[/green]")
        else:
            console.print("\n  [yellow][!] No JPGs updated — no images found in "
                          "jpg*/jpeg* folders, or exiftool failed (see log).[/yellow]")
    except Exception as e:
        console.print(f"\n  [red][!] Error: {e}[/red]")
        logger.error(str(e), exc_info=True)

    _wait_enter()


# ══════════════════════════════════════════════════════════════════════════
# 9 · RELIGHTLAB RDF-PLUGIN INSTALL
# Patch relight sources, copy the plugin files, and build with cmake + make.
# ══════════════════════════════════════════════════════════════════════════

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

    if 'addTab(metadata_frame' not in content:
        patched = False
        for q, m in [('"Queue"', '"Metadata"'), ('tr("Queue")', 'tr("Metadata")')]:
            inline = f'tabs->addTab(queue_frame = new QueueFrame, {q})'
            if inline in content:
                content = content.replace(
                    inline,
                    f'queue_frame = new QueueFrame;\n\tmetadata_frame = new MetadataFrame(this);\n\ttabs->addTab(queue_frame, {q});\n\ttabs->addTab(metadata_frame, {m})'
                )
                modified = True
                patched = True
                break
        if not patched:
            if 'new MetadataFrame' not in content:
                if 'queue_frame = new QueueFrame' in content:
                    content = content.replace(
                        'queue_frame = new QueueFrame',
                        'metadata_frame = new MetadataFrame(this);\n\tqueue_frame = new QueueFrame'
                    )
                    modified = True
                else:
                    print("      [!] mainwindow.cpp: QueueFrame constructor not found — MetadataFrame init skipped")
            tab_added = False
            for q, m in [('"Queue"', '"Metadata"'), ('tr("Queue")', 'tr("Metadata")')]:
                anchor = f'queue_frame, {q})'
                if anchor in content:
                    content = content.replace(
                        anchor,
                        f'queue_frame, {q});\n\ttabs->addTab(metadata_frame, {m})'
                    )
                    modified = True
                    tab_added = True
                    break
            if not tab_added:
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
                'class ZoomOverview;\nclass QCheckBox;\nclass QJsonObject;'
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
                'void updateNPlanes();\n\tvoid exportRdfSidecar(const QJsonObject &task);'
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
                'rdf_check = new QCheckBox("Export provenance JSON", this);\n'
                '\t\t\t\trdf_check->setChecked(true);\n'
                '\t\t\t\trdf_check->setToolTip("Automatically write an ontology-neutral provenance JSON sidecar alongside the RTI output.");\n'
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
                '\t\t\t\texportRdfSidecar(task);\n'
                '\t\t});\n'
                '\t}\n}',
                1
            )
            modified = True
        else:
            print("      [!] rtiframe.cpp: emit processStarted() anchor not found — auto-export call skipped")

    if 'void RtiFrame::exportRdfSidecar(' not in content and '#include "rdfexport.h"' in content:
        # Only append the implementation to a genuine, wired rtiframe.cpp (rdfexport.h present);
        # never inject the method into an unrelated file that lacks the required include.
        sidecar_impl = (
            '\n\nvoid RtiFrame::exportRdfSidecar(const QJsonObject &task) {\n'
            '\t// Automatic, ontology-neutral provenance sidecar.\n'
            '\t// Naming mirrors the manual TTL: e.g. F01RTI08-ptm.json\n'
            '\tQString p = task.value("parameters").toObject().value("path").toString();\n'
            '\tif (p.isEmpty()) return;\n'
            '\tif (p.endsWith(\'/\') || p.endsWith(\'\\\\\')) p.chop(1);\n'
            '\tQFileInfo fi(p);\n'
            '\tQDir    sessionDir = fi.dir();\n'
            '\tQString session    = sessionDir.dirName();\n'
            '\tQDir    figureDir  = sessionDir;\n'
            '\tfigureDir.cdUp();\n'
            '\tQString figure     = figureDir.dirName();\n'
            '\tsession.remove(\'-\');\n'
            '\tQString folderName = fi.fileName();\n'
            '\tQString json_name = figure + session + "-" + folderName + ".json";\n'
            '\tQString json_path = p + "/" + json_name;\n'
            '\n'
            '\tQString error;\n'
            '\tif (!RdfExport::writeProvenanceJson(task, json_path, error))\n'
            '\t\tQMessageBox::warning(this, "Provenance Export", "Could not write provenance JSON:\\n" + error);\n'
            '}\n'
        )
        content += sidecar_impl
        modified = True

    if modified:
        with open(cpp_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return modified


def _git_reset_patched(relight_src, files, logger):
    """Restore previously patched relight files to their pristine state so a fresh
    patch can be applied cleanly. Without this, re-installing an updated plugin onto
    an already-patched source is skipped (the guards see the old patch and bail),
    leaving the OLD behaviour in place. Only acts when relight_src is a git work tree;
    the files we patch are upstream relight files we never hand-edit, so resetting them
    is safe. Copied plugin files (rdfexport/metadataframe) are untracked and untouched."""
    is_git = subprocess.run(
        ['git', '-C', relight_src, 'rev-parse', '--is-inside-work-tree'],
        capture_output=True, text=True
    ).returncode == 0
    if not is_git:
        print("      [!] Not a git repo — cannot auto-reset old patch; existing wiring kept.")
        logger.info("git reset skipped: not a git repo")
        return False
    res = subprocess.run(
        ['git', '-C', relight_src, 'checkout', '--'] + files,
        capture_output=True, text=True
    )
    if res.returncode != 0:
        print(f"      [!] git checkout failed: {res.stderr.strip()}")
        logger.info(f"git reset failed: {res.stderr.strip()}")
        return False
    print("      OK — previous patch reset (clean source)")
    logger.info("git reset patched files: OK")
    return True


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

    print("\n[2b] Resetting any previous plugin patch...")
    _git_reset_patched(relight_src,
                       [cmake_path, mw_h_path, mw_cpp_path, rti_h_path, rti_cpp_path],
                       logger)

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


# ══════════════════════════════════════════════════════════════════════════
# 10 · LOG VIEWER
# List and page through the pipeline log files under 04-logs/.
# ══════════════════════════════════════════════════════════════════════════

_LOG_MODULES = ['jpg-metadata', 'knowledge-graph', 'rdf-plugin']


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


# ══════════════════════════════════════════════════════════════════════════
# 11 · HOME SCREEN & ENTRY POINT
# Banner, menu loop and first-run directory scaffolding.
# ══════════════════════════════════════════════════════════════════════════

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
            run_jpg_metadata()
        elif val == '2':
            run_rdf_plugin_install()
        elif val == '3':
            run_knowledge_graph()
        elif val == '4':
            run_log_viewer()


if __name__ == '__main__':
    for d in [DATASETS_DIR, OUTPUTS_DIR, KG_OUTPUTS_DIR,
              os.path.join(LOGS_DIR, 'knowledge-graph'),
              os.path.join(LOGS_DIR, 'rdf-plugin')]:
        os.makedirs(d, exist_ok=True)

    _example = os.path.join(DATASETS_DIR, 'Site Name', 'Object-01', 'RTI-01')
    for sub in ('raw', 'jpg', 'jpg-export'):
        os.makedirs(os.path.join(_example, sub), exist_ok=True)

    main()
