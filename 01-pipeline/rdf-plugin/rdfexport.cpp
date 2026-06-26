/*
 * rdfexport.cpp  —  RDF/Turtle export for RelightLab (Sem-RTI pipeline)
 *
 * Generates Section E: the RTI processing output distribution, using the same
 * ontologies and 17-prefix namespace as the Sem-RTI SPARQL Anything pipeline.
 *
 * Ontology alignment
 * ──────────────────
 *  Equipment         chs:Hardware              (NOT a-dd:TechnicalEquipment)
 *  Measurement value muapit:value              (NOT rdf:value / a-dd:hasValue)
 *  Equip config      chs:EquipmentConfiguration
 *  Equip property    chs:usesEquipment
 *  Distribution      dcat:Distribution
 *  Measurements      named IRIs rm-meas:{id}-{type}
 *
 * Modular layout
 * ──────────────
 *  §1  String helpers
 *  §2  GPS rational → decimal degrees
 *  §3  XMP extraction from JPEG
 *  §4  XMP XML parser
 *  §5  info.json parser
 *  §6  readFromProject (public)
 *  §7  Turtle writer (public)
 */

#include "rdfexport.h"

#include "../src/exif.h"
#include "../src/project.h"
#include "../src/rti/rtiparameters.h"
#include "../src/rti.h"

#include <QFile>
#include <QTextStream>
#include <QDir>
#include <QFileInfo>
#include <QDateTime>
#include <QRegularExpression>
#include <QXmlStreamReader>
#include <QStack>
#include <QCryptographicHash>
#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>

// ═══════════════════════════════════════════════════════════════════════════
//  §1  String helpers
// ═══════════════════════════════════════════════════════════════════════════

QString RdfExport::slugify(const QString &s)
{
    QString out;
    out.reserve(s.size());
    for (QChar c : s) {
        if (c.isLetterOrNumber())
            out += c;
        else if (!out.isEmpty() && out.back() != '_')
            out += '_';
    }
    while (out.endsWith('_')) out.chop(1);
    return out;
}

QString RdfExport::rtiTypeLabel(const QString &type)
{
    const QString t = type.toLower();
    if (t == "ptm")      return "Polynomial Texture Map (PTM)";
    if (t == "hsh")      return "Hemispherical Harmonics (HSH)";
    if (t == "rbf")      return "Radial Basis Function (RBF)";
    if (t == "bilinear") return "Bilinear Interpolation";
    if (t == "neural")   return "Neural RTI";
    return type;
}

QString RdfExport::colorspaceLabel(const QString &cs)
{
    const QString c = cs.toLower();
    if (c == "rgb")  return "RGB";
    if (c == "lrgb") return "Luminance+RGB (LRGB)";
    if (c == "ycc")  return "YCbCr (YCC)";
    if (c == "mrgb") return "MRGB";
    if (c == "mycc") return "MYCC";
    return cs;
}

QString RdfExport::colorProfileModeLabel(int mode)
{
    // ColorProfileMode enum: 0=LINEAR_RGB, 1=SRGB, 2=DISPLAY_P3
    switch (mode) {
        case 0:  return "Linear RGB";
        case 1:  return "sRGB";
        case 2:  return "Display P3";
        default: return "sRGB";
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  §2  GPS rational → decimal degrees
// ═══════════════════════════════════════════════════════════════════════════

static double gpsToDecimal(const QVariant &v)
{
    const QVariantList list = v.toList();
    if (list.size() < 3) return v.toDouble();
    return list[0].toDouble()
         + list[1].toDouble() / 60.0
         + list[2].toDouble() / 3600.0;
}

// ═══════════════════════════════════════════════════════════════════════════
//  §3  XMP extraction from JPEG
//
//  XMP is stored in an APP1 marker (FF E1) beginning with the Adobe
//  namespace URI "http://ns.adobe.com/xap/1.0/" + null byte + UTF-8 XML.
//  We scan the first 2 MB to locate this marker.
// ═══════════════════════════════════════════════════════════════════════════

static QByteArray extractXmpFromJpeg(const QString &path)
{
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) return {};

    QByteArray data = f.read(2 * 1024 * 1024);
    f.close();

    if (data.size() < 4) return {};
    if ((quint8)data[0] != 0xFF || (quint8)data[1] != 0xD8) return {};

    const QByteArray kXmpNs = "http://ns.adobe.com/xap/1.0/";
    int pos = 2;

    while (pos + 4 <= data.size()) {
        if ((quint8)data[pos] != 0xFF) break;
        quint8 marker = (quint8)data[pos + 1];

        if (marker == 0xDA || marker == 0xD9) break;
        if (marker == 0x01 || (marker >= 0xD0 && marker <= 0xD9)) {
            pos += 2;
            continue;
        }
        if (pos + 4 > data.size()) break;
        int segLen = ((quint8)data[pos + 2] << 8) | (quint8)data[pos + 3];

        if (marker == 0xE1) {
            int hdrStart = pos + 4;
            if (hdrStart + kXmpNs.size() + 1 <= data.size()
                && data.mid(hdrStart, kXmpNs.size()) == kXmpNs)
            {
                int payloadStart = hdrStart + kXmpNs.size() + 1;
                int payloadLen   = segLen - 2 - kXmpNs.size() - 1;
                if (payloadLen > 0 && payloadStart + payloadLen <= data.size())
                    return data.mid(payloadStart, payloadLen);
            }
        }
        pos += 2 + segLen;
    }
    return {};
}

// ═══════════════════════════════════════════════════════════════════════════
//  §4  XMP XML parser
//
//  Fills RdfMetadata from the XMP RDF/XML packet embedded in the source
//  JPEG.  Fields already set (e.g. from a user override) are never
//  overwritten (XMP_SET guard).
// ═══════════════════════════════════════════════════════════════════════════

#define XMP_SET(field, value) \
    do { if ((field).isEmpty() && !(value).isEmpty()) (field) = (value); } while(0)

static void enrichFromXmp(const QByteArray &xmpData, RdfMetadata &meta)
{
    if (xmpData.isEmpty()) return;

    static const QString kDC        = "http://purl.org/dc/elements/1.1/";
    static const QString kXmp       = "http://ns.adobe.com/xap/1.0/";
    static const QString kPS        = "http://ns.adobe.com/photoshop/1.0/";
    static const QString kIptc      = "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/";
    static const QString kIptcExt   = "http://iptc.org/std/Iptc4xmpExt/2008-02-29/";
    static const QString kXmpRights = "http://ns.adobe.com/xap/1.0/rights/";

    QXmlStreamReader xml(xmpData);
    xml.setNamespaceProcessing(true);

    QStack<QPair<QString,QString>> stack;

    auto inside = [&](const QString &ns, const QString &local) -> bool {
        for (const auto &e : stack)
            if (e.first == ns && e.second == local) return true;
        return false;
    };

    auto applyAttr = [&](const QString &ns, const QString &name, const QString &val) {
        if (val.isEmpty()) return;
        if (ns == kDC) {
            if (name == "rights") XMP_SET(meta.copyright, val);
        } else if (ns == kPS) {
            if      (name == "City")            { XMP_SET(meta.city,       val); }
            else if (name == "State")           { XMP_SET(meta.province,   val); }
            else if (name == "Country")         { XMP_SET(meta.country,    val); }
            else if (name == "AuthorsPosition") { XMP_SET(meta.artistRole, val); }
            else if (name == "Credit") {
                if (meta.institution.isEmpty()) {
                    QStringList p = val.split(" / ");
                    meta.institution = (p.size() > 1) ? p.last().trimmed() : val;
                }
            }
        } else if (ns == kIptc) {
            if      (name == "Location")        { XMP_SET(meta.siteName,    val); }
            else if (name == "CiUrlWork")       { XMP_SET(meta.orcid,       val); }
            else if (name == "AuthorsPosition") { XMP_SET(meta.artistRole,  val); }
            else if (name == "CreatorJobTitle") { XMP_SET(meta.artistRole,  val); }
            else if (name == "CiEmailWork")     { XMP_SET(meta.artistEmail, val); }
        } else if (ns == kXmpRights) {
            if (name == "WebStatement") { XMP_SET(meta.licenseUrl, val); }
        } else if (ns == kIptcExt) {
            if (name == "OriginalFileName") { XMP_SET(meta.rawSourceFile, val); }
        }
    };

    while (!xml.atEnd() && !xml.hasError()) {
        xml.readNext();

        if (xml.isStartElement()) {
            stack.push({ xml.namespaceUri().toString(), xml.name().toString() });
            for (const QXmlStreamAttribute &attr : xml.attributes())
                applyAttr(attr.namespaceUri().toString(),
                          attr.name().toString(),
                          attr.value().toString().trimmed());

        } else if (xml.isEndElement()) {
            if (!stack.isEmpty()) stack.pop();

        } else if (xml.isCharacters() && !xml.isWhitespace()) {
            const QString text = xml.text().toString().trimmed();
            if (text.isEmpty()) continue;

            if (inside(kDC,   "creator"))           { XMP_SET(meta.artistName,   text); }
            if (inside(kDC,   "title"))              { XMP_SET(meta.datasetId,    text); }
            if (inside(kDC,   "rights"))             { XMP_SET(meta.copyright,    text); }
            if (inside(kXmp,  "Nickname"))           { XMP_SET(meta.featureId,    text); }
            if (inside(kIptc, "Location"))           { XMP_SET(meta.siteName,     text); }
            if (inside(kIptc, "CiUrlWork"))          { XMP_SET(meta.orcid,        text); }
            if (inside(kIptc, "AuthorsPosition"))    { XMP_SET(meta.artistRole,   text); }
            if (inside(kIptc, "CreatorJobTitle"))    { XMP_SET(meta.artistRole,   text); }
            if (inside(kIptc, "CiEmailWork"))        { XMP_SET(meta.artistEmail,  text); }
            if (inside(kPS,   "City"))               { XMP_SET(meta.city,         text); }
            if (inside(kPS,   "State"))              { XMP_SET(meta.province,     text); }
            if (inside(kPS,   "Country"))            { XMP_SET(meta.country,      text); }
            if (inside(kPS,   "AuthorsPosition"))    { XMP_SET(meta.artistRole,   text); }
            if (inside(kPS,   "Credit")) {
                if (meta.institution.isEmpty()) {
                    QStringList p = text.split(" / ");
                    meta.institution = (p.size() > 1) ? p.last().trimmed() : text;
                }
            }
            if (inside(kXmpRights, "WebStatement"))    { XMP_SET(meta.licenseUrl,   text); }
            if (inside(kIptcExt,   "OriginalFileName")){ XMP_SET(meta.rawSourceFile, text); }
        }
    }
}
#undef XMP_SET

// ═══════════════════════════════════════════════════════════════════════════
//  §5  info.json parser
//
//  Reads the JSON file produced by RelightLab in the RTI output directory.
//  Safe to call with an empty path or a path where info.json is absent.
// ═══════════════════════════════════════════════════════════════════════════

void RdfExport::readFromInfoJson(const QString &outputDir, RdfMetadata &meta)
{
    if (outputDir.isEmpty()) return;

    const QString jsonPath = QDir(outputDir).filePath("info.json");
    QFile f(jsonPath);
    if (!f.open(QIODevice::ReadOnly)) return;

    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    f.close();

    if (err.error != QJsonParseError::NoError || !doc.isObject()) return;

    const QJsonObject obj = doc.object();

    meta.rtiWidth        = obj.value("width").toInt();
    meta.rtiHeight       = obj.value("height").toInt();
    meta.pixelSizeInMM   = obj.value("pixelSizeInMM").toDouble();
    meta.rtiType         = obj.value("type").toString();
    meta.rtiColorspace   = obj.value("colorspace").toString();
    meta.rtiNPlanes      = obj.value("nplanes").toInt();
    meta.rtiQuality      = obj.value("quality").toInt();
    meta.rtiColorProfile = obj.value("colorProfile").toString();
    meta.hasRtiOutput    = (meta.rtiWidth > 0 && meta.rtiHeight > 0);
}

// ═══════════════════════════════════════════════════════════════════════════
//  §6  readFromProject  (public)
// ═══════════════════════════════════════════════════════════════════════════

RdfMetadata RdfExport::readFromProject(const Project &project)
{
    RdfMetadata meta;
    meta.licenseUrl = "https://creativecommons.org/licenses/by/4.0/";
    meta.kgBaseUri  = "https://w3id.org/rupemagna/resource/";

    for (const Image &img : project.images)
        if (!img.skip) ++meta.imageCount;

    QString imagePath;
    for (const Image &img : project.images) {
        if (!img.skip) { imagePath = project.dir.filePath(img.filename); break; }
    }
    if (imagePath.isEmpty()) return meta;

    // ── EXIF (binary) — numeric/binary fields only ───────────────────────────
    // Textual fields (author, title) use XMP below to preserve full UTF-8.
    Exif exif;
    try { exif.parse(imagePath); } catch (...) {}

    meta.cameraMake  = exif.value(Exif::Make).toString().trimmed();
    meta.cameraModel = exif.value(Exif::Model).toString().trimmed();

    if (exif.contains(Exif::ISOSpeedRatings))
        meta.iso = exif[Exif::ISOSpeedRatings].toInt();
    if (exif.contains(Exif::FNumber))
        meta.fnumber = exif[Exif::FNumber].toDouble();
    if (exif.contains(Exif::ExposureTime))
        meta.exposureTime = exif[Exif::ExposureTime].toDouble();
    if (exif.contains(Exif::FocalLength))
        meta.focalLength = exif[Exif::FocalLength].toDouble();

    {
        QString ds = exif.value(Exif::DateTimeOriginal).toString();
        if (ds.isEmpty()) ds = exif.value(Exif::DateTime).toString();
        if (!ds.isEmpty())
            meta.acquisitionDate = QDateTime::fromString(ds, "yyyy:MM:dd HH:mm:ss");
    }

    if (exif.contains(Exif::GpsLatitude) && exif.contains(Exif::GpsLongitude)) {
        meta.gpsLat = gpsToDecimal(exif[Exif::GpsLatitude]);
        if (exif.value(Exif::GpsLatitudeRef).toString()  == "S") meta.gpsLat = -meta.gpsLat;
        meta.gpsLon = gpsToDecimal(exif[Exif::GpsLongitude]);
        if (exif.value(Exif::GpsLongitudeRef).toString() == "W") meta.gpsLon = -meta.gpsLon;
        if (exif.contains(Exif::GpsAltitude))
            meta.gpsAlt = exif[Exif::GpsAltitude].toDouble();
        meta.hasGps = (meta.gpsLat != 0.0 || meta.gpsLon != 0.0);
    }

    // ── XMP (UTF-8 XML) — textual fields ────────────────────────────────────
    enrichFromXmp(extractXmpFromJpeg(imagePath), meta);

    // ── Parse sessionId / figureId / siteName from dc:title ─────────────────
    // Title format written by run-pipeline.sh: "Rupe Magna - [F09] - [RTI-35]"
    if (!meta.datasetId.isEmpty()) {
        const QString fullTitle = meta.datasetId;

        if (meta.siteName.isEmpty()) {
            const int idx = fullTitle.indexOf(" - [");
            if (idx > 0) meta.siteName = fullTitle.left(idx).trimmed();
        }

        static const QRegularExpression reBracket("\\[([^\\]]+)\\]");
        QRegularExpressionMatchIterator it = reBracket.globalMatch(fullTitle);
        QStringList tokens;
        while (it.hasNext()) tokens << it.next().captured(1);

        if (!tokens.isEmpty() && meta.featureId.isEmpty())
            meta.featureId = tokens.at(0);                  // "F09"
        if (tokens.size() >= 2)
            meta.datasetId = tokens.at(1);                  // "RTI-35"
    }

    // ── EXIF Artist — UTF-8 reinterpretation fallback ───────────────────────
    // Relight's EXIF parser uses fromLatin1(); ExifTool writes UTF-8 into the
    // ASCII field.  Re-decode the Latin-1 bytes as UTF-8 to recover non-ASCII
    // characters (e.g. ğ, ş in "Hüseyin Erdoğan").
    if (meta.artistName.isEmpty()) {
        const QString latin1 = exif.value(Exif::Artist).toString().trimmed();
        if (!latin1.isEmpty())
            meta.artistName = QString::fromUtf8(latin1.toLatin1());
    }

    // ── SHA-256 checksum (first source image) ────────────────────────────────
    {
        QFile imgFile(imagePath);
        if (imgFile.open(QIODevice::ReadOnly)) {
            QCryptographicHash hash(QCryptographicHash::Sha256);
            hash.addData(&imgFile);
            meta.imageChecksumSha256 = hash.result().toHex();
        }
    }

    return meta;
}

// ═══════════════════════════════════════════════════════════════════════════
//  §7  Turtle writer  (public)
//
//  Generates Section E: the RTI distribution produced by RelightLab.
//  Output is designed to be merged with rupe-magna-complete.ttl.
//
//  Namespace alignment with Sem-RTI pipeline
//  ──────────────────────────────────────────
//  rm-data:   dataset/           dcat:Dataset (existing, from pipeline)
//  rm-dist:   distribution/      dcat:Distribution (new — RTI output)
//  rm-mcoll:  measurement-coll/  a-dd:MeasurementCollection
//  rm-meas:   measurement/       a-dd:Measurement (named IRIs)
//  rm-mtype:  measurement-type/  a-dd:MeasurementType
//  rm-unit:   measurement-unit/  muapit:MeasurementUnit
//  rm-equip:  equipment/         chs:Hardware
//  rm-agent:  agent/             core:Agent
// ═══════════════════════════════════════════════════════════════════════════

bool RdfExport::write(const Project       &project,
                      const RtiParameters *params,
                      const RdfMetadata   &meta,
                      const QString       &outputPath,
                      QString             &error)
{
    QFile file(outputPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        error = "Cannot write to: " + outputPath;
        return false;
    }

    QTextStream ts(&file);
    ts.setEncoding(QStringConverter::Utf8);

    // ── Read info.json if params provides an output directory ────────────────
    RdfMetadata m = meta;
    if (params && !params->path.isEmpty() && !m.hasRtiOutput)
        readFromInfoJson(params->path, m);

    // ── Resolve KG base URI ──────────────────────────────────────────────────
    QString base = m.kgBaseUri.trimmed();
    if (base.isEmpty()) base = "https://w3id.org/rupemagna/resource/";
    if (!base.endsWith('/')) base += '/';

    // ── Session and figure identifiers ───────────────────────────────────────
    const QString sessionId = m.datasetId.trimmed();   // "RTI-35"
    const QString figureId  = m.featureId.trimmed();   // "F09"
    const QString siteLabel = m.siteName.trimmed();

    // ── Agent IRI (ORCID-based) ──────────────────────────────────────────────
    QString agentSlug;
    if (!m.orcid.isEmpty()) {
        agentSlug = m.orcid;
        agentSlug.remove(QRegularExpression("https?://orcid\\.org/"));
        agentSlug.replace('-', '_');
        agentSlug = "agent_" + agentSlug;
    } else if (!m.artistName.isEmpty()) {
        agentSlug = "agent_" + slugify(m.artistName);
    } else {
        agentSlug = "agent_unknown";
    }

    // ── Distribution label ───────────────────────────────────────────────────
    // Prefer the output folder name (e.g. "ptm-deepzoom", "ptm2") so that
    // multiple exports from the same session each get a unique IRI.
    QString distSuffix;
    if (params && !params->path.isEmpty()) {
        QString folder = params->path;
        while (folder.endsWith('/') || folder.endsWith('\\')) folder.chop(1);
        distSuffix = QDir(folder).dirName();
    }
    if (distSuffix.isEmpty()) {
        if (!m.rtiType.isEmpty())
            distSuffix = m.rtiType.toLower();
        else if (params)
            distSuffix = (params->basis == Rti::PTM) ? "ptm" : "rti";
        else
            distSuffix = "rti";
    }

    const QString distId  = sessionId + "-" + distSuffix;
    const QString mcollId = sessionId + "-" + distSuffix;

    const QString now     = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    const QString acqDate = m.acquisitionDate.isValid()
                            ? m.acquisitionDate.toString("yyyy-MM-dd")
                            : now.left(10);

    const QString licUrl  = m.licenseUrl.isEmpty()
                            ? "https://creativecommons.org/licenses/by/4.0/"
                            : m.licenseUrl;

    // Human-readable label: "The Map-like Figure (F09), RTI-35, Rupe Magna"
    QString datasetLabel;
    {
        QStringList parts;
        if (!siteLabel.isEmpty())  parts << siteLabel;
        if (!figureId.isEmpty())   parts << "[" + figureId + "]";
        if (!sessionId.isEmpty())  parts << "[" + sessionId + "]";
        datasetLabel = parts.isEmpty() ? project.name : parts.join(" - ");
    }

    const QString rtiTypeStr = m.hasRtiOutput
                               ? rtiTypeLabel(m.rtiType)
                               : (params ? (params->basis == Rti::PTM
                                            ? "Polynomial Texture Map (PTM)"
                                            : "RTI") : "RTI");

    // ── File header ──────────────────────────────────────────────────────────
    ts << "# Turtle RDF — Sem-RTI Section E: RTI Processing Output\n"
       << "# Generated by RelightLab " << QCoreApplication::applicationVersion()
       << "  <https://vcg.isti.cnr.it/relight/>\n"
       << "# Timestamp : " << now << "\n"
       << "# Project   : " << project.name << "\n"
       << "# Session   : " << (sessionId.isEmpty() ? "(unknown)" : sessionId) << "\n"
       << "#\n"
       << "# This file describes the RTI distribution produced by RelightLab.\n"
       << "# Merge with rupe-magna-complete.ttl to form the full Knowledge Graph.\n"
       << "#\n\n";

    // ── Namespace declarations (aligned with Sem-RTI pipeline) ───────────────
    ts << "@prefix rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
       << "@prefix rdfs:     <http://www.w3.org/2000/01/rdf-schema#> .\n"
       << "@prefix xsd:      <http://www.w3.org/2001/XMLSchema#> .\n"
       << "@prefix owl:      <http://www.w3.org/2002/07/owl#> .\n"
       << "@prefix foaf:     <http://xmlns.com/foaf/0.1/> .\n"
       << "@prefix dct:      <http://purl.org/dc/terms/> .\n"
       << "@prefix dcat:     <http://www.w3.org/ns/dcat#> .\n"
       << "@prefix schema:   <https://schema.org/> .\n"
       << "@prefix arco:     <https://w3id.org/arco/ontology/arco/> .\n"
       << "@prefix a-cd:     <https://w3id.org/arco/ontology/context-description/> .\n"
       << "@prefix a-dd:     <https://w3id.org/arco/ontology/denotative-description/> .\n"
       << "@prefix core:     <https://w3id.org/arco/ontology/core/> .\n"
       << "@prefix chs:      <http://www.ontologydesignpatterns.org/cp/owl/culturalheritagesurvey.owl#> .\n"
       << "@prefix muapit:   <http://www.ontologydesignpatterns.org/ont/dul/muapit.owl#> .\n"
       << "@prefix geosparql: <http://www.opengis.net/ont/geosparql#> .\n"
       << "@prefix prov:     <http://www.w3.org/ns/prov#> .\n"
       // Sem-RTI 17-prefix namespace (category-specific)
       << "@prefix rm-data:  <" << base << "dataset/> .\n"
       << "@prefix rm-dist:  <" << base << "distribution/> .\n"
       << "@prefix rm-mcoll: <" << base << "measurement-collection/> .\n"
       << "@prefix rm-meas:  <" << base << "measurement/> .\n"
       << "@prefix rm-mtype: <" << base << "measurement-type/> .\n"
       << "@prefix rm-unit:  <" << base << "measurement-unit/> .\n"
       << "@prefix rm-equip: <" << base << "equipment/> .\n"
       << "@prefix rm-agent:  <" << base << "agent/> .\n"
       << "@prefix rm-survey: <" << base << "survey/> .\n\n";

    // ════════════════════════════════════════════════════════════════════════
    //  SECTION E.1 — Link existing dataset to new RTI distribution
    //
    //  rm-data:{sessionId} already exists in the pipeline output.
    //  We add dcat:distribution pointing to the new RTI distribution.
    // ════════════════════════════════════════════════════════════════════════
    if (!sessionId.isEmpty()) {
        ts << "# ── E.1  Link dataset → RTI distribution ────────────────────────────\n"
           << "rm-data:" << sessionId << "\n"
           << "    dcat:distribution rm-dist:" << distId << " .\n\n";
    }

    // ════════════════════════════════════════════════════════════════════════
    //  SECTION E.2 — RTI distribution  (dcat:Distribution)
    //
    //  Describes the output produced by RelightLab: type, dimensions, format,
    //  creator, licence, and measurement collection for technical parameters.
    // ════════════════════════════════════════════════════════════════════════
    // Resolve survey URI for prov:wasGeneratedBy
    const QString surveyUri = sessionId.isEmpty()
                              ? QString()
                              : "rm-survey:" + sessionId;

    // Color profile mode label (from params enum)
    const QString colorProfileModeStr = params
                                        ? colorProfileModeLabel(static_cast<int>(params->colorProfileMode))
                                        : QString("sRGB");

    // Openlime flag (from params)
    const bool openlime = params ? params->openlime : false;

    // Crop origin from project (x, y, angle — w/h already in schema:width/height)
    const QString cropOriginStr = QString("x=%1 y=%2 angle=%3")
                                  .arg(project.crop.left())
                                  .arg(project.crop.top())
                                  .arg(project.crop.angle, 0, 'f', 1);

    ts << "# ── E.2  RTI distribution (dcat:Distribution) ───────────────────────────\n"
       << "rm-dist:" << distId << "\n"
       << "    a owl:NamedIndividual , dcat:Distribution , chs:Result ;\n";

    // Title
    {
        QString title = rtiTypeStr + " output — " + datasetLabel;
        ts << "    dct:title         \"" << title << "\"@en ;\n";
    }

    // Description
    {
        QString desc = rtiTypeStr + " processing output generated by RelightLab "
                       + QCoreApplication::applicationVersion()
                       + " from " + QString::number(m.imageCount) + " source JPEG images";
        if (!siteLabel.isEmpty()) desc += " at " + siteLabel;
        desc += ".";
        ts << "    dct:description   \"" << desc << "\"@en ;\n";
    }

    // Format
    ts << "    dct:format        \"" << rtiTypeStr << " (Web — JSON + JPEG tiles)\"^^xsd:string ;\n";

    // Creator
    if (!m.artistName.isEmpty() || !m.orcid.isEmpty())
        ts << "    dct:creator       rm-agent:" << agentSlug << " ;\n";

    // Issued date
    ts << "    dct:issued        \"" << acqDate << "\"^^xsd:date ;\n";

    // License
    ts << "    dct:license       <" << licUrl << "> ;\n";

    // Processing timestamp
    ts << "    dct:created       \"" << now << "\"^^xsd:dateTime ;\n";

    // ODP alignment: this distribution was generated by the RTI survey
    if (!surveyUri.isEmpty())
        ts << "    prov:wasGeneratedBy " << surveyUri << " ;\n";

    // Spatial coverage (GPS coordinates as WKT when available)
    if (m.hasGps)
        ts << "    dct:spatial       [ a geosparql:Geometry ;\n"
           << "        geosparql:asWKT\n"
           << "            \"POINT(" << QString::number(m.gpsLon, 'f', 6)
           << " " << QString::number(m.gpsLat, 'f', 6)
           << ")\"^^geosparql:wktLiteral ] ;\n";

    // Image dimensions (schema: vocabulary — widely understood)
    if (m.hasRtiOutput && m.rtiWidth > 0)
        ts << "    schema:width      " << m.rtiWidth  << " ;\n"
           << "    schema:height     " << m.rtiHeight << " ;\n";

    // Link to measurement collection
    ts << "    a-dd:hasMeasurementCollection rm-mcoll:" << mcollId << " ;\n";

    // Label
    ts << "    rdfs:label        \"" << rtiTypeStr << " distribution — "
       << sessionId << "\"@en .\n\n";

    // ════════════════════════════════════════════════════════════════════════
    //  SECTION E.3 — MeasurementCollection (technical RTI parameters)
    //
    //  Each parameter is a named individual a-dd:Measurement with muapit:value.
    //  Named IRIs follow the pipeline pattern: rm-meas:{sessionId}-{distSuffix}-{type}
    // ════════════════════════════════════════════════════════════════════════
    const QString measBase = sessionId + "-" + distSuffix + "-";

    // Determine which measurements to emit
    const bool hasNPlanes        = m.hasRtiOutput && m.rtiNPlanes > 0;
    const bool hasPixelSize      = m.hasRtiOutput && m.pixelSizeInMM > 0.0;
    const bool hasQuality        = m.hasRtiOutput && m.rtiQuality > 0;
    const bool hasType           = !m.rtiType.isEmpty();
    const bool hasCS             = !m.rtiColorspace.isEmpty();
    const bool hasWebLayout      = !m.rtiWebLayout.isEmpty();
    const bool hasColorProfile   = !colorProfileModeStr.isEmpty();
    const bool hasOpenlime       = params != nullptr;
    const bool hasCropOrigin     = (project.crop.left() != 0
                                    || project.crop.top() != 0
                                    || project.crop.angle != 0.0);

    // MeasurementCollection header
    ts << "# ── E.3  RTI measurement collection (a-dd:MeasurementCollection) ──────\n"
       << "rm-mcoll:" << mcollId << "\n"
       << "    a owl:NamedIndividual , a-dd:MeasurementCollection ;\n"
       << "    rdfs:label \"RTI processing parameters — " << sessionId << "\"@en";

    if (hasNPlanes)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "nplanes";
    if (hasPixelSize)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "pixelsize";
    if (hasQuality)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "quality";
    if (hasType)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "type";
    if (hasCS)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "colorspace";
    if (hasWebLayout)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "weblayout";
    if (hasColorProfile)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "colorprofilemode";
    if (hasOpenlime)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "openlime";
    if (hasCropOrigin)
        ts << " ;\n    a-dd:hasMeasurement rm-meas:" << measBase << "croporigin";

    ts << " .\n\n";

    // ── Individual Measurement nodes ─────────────────────────────────────────

    // Number of planes (PTM polynomial order)
    if (hasNPlanes) {
        ts << "rm-meas:" << measBase << "nplanes\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-nplanes ;\n"
           << "    muapit:value \"" << m.rtiNPlanes << "\"^^xsd:integer ;\n"
           << "    rdfs:label \"" << m.rtiType.toUpper() << " planes: " << m.rtiNPlanes << " — " << sessionId << "\"@en .\n\n";
    }

    // Pixel size in mm (physical scale)
    if (hasPixelSize) {
        ts << "rm-meas:" << measBase << "pixelsize\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:pixel-size ;\n"
           << "    a-dd:hasMeasurementUnit rm-unit:millimetre ;\n"
           << "    muapit:value \"" << QString::number(m.pixelSizeInMM, 'g', 7) << "\"^^xsd:decimal ;\n"
           << "    rdfs:label \"Pixel size in mm — " << sessionId << "\"@en .\n\n";
    }

    // JPEG compression quality
    if (hasQuality) {
        ts << "rm-meas:" << measBase << "quality\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:jpeg-quality ;\n"
           << "    muapit:value \"" << m.rtiQuality << "\"^^xsd:integer ;\n"
           << "    rdfs:label \"JPEG quality: " << m.rtiQuality << " — " << sessionId << "\"@en .\n\n";
    }

    // RTI basis type
    if (hasType) {
        ts << "rm-meas:" << measBase << "type\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-basis-type ;\n"
           << "    muapit:value \"" << m.rtiType.toUpper() << "\"^^xsd:string ;\n"
           << "    rdfs:label \"RTI basis type: " << m.rtiType.toUpper() << " — " << sessionId << "\"@en .\n\n";
    }

    // Colour space
    if (hasCS) {
        ts << "rm-meas:" << measBase << "colorspace\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-colorspace ;\n"
           << "    muapit:value \"" << colorspaceLabel(m.rtiColorspace) << "\"^^xsd:string ;\n"
           << "    rdfs:label \"RTI colour space — " << sessionId << "\"@en .\n\n";
    }

    // ════════════════════════════════════════════════════════════════════════
    //  SECTION E.4 — MeasurementType definitions (for new types not in shared.ttl)
    //
    //  These four types are specific to RTI processing output and are not
    //  declared in the pipeline's shared.ttl.  Include them inline so the
    //  sidecar TTL is self-contained when loaded independently.
    // Web layout
    if (hasWebLayout) {
        const QString wlLabel = [&]() -> QString {
            const QString w = m.rtiWebLayout.toLower();
            if (w == "deepzoom") return "DeepZoom tiles";
            if (w == "tarzoom")  return "TarZoom";
            if (w == "itarzoom") return "ITarZoom";
            return "Images (plain)";
        }();
        ts << "rm-meas:" << measBase << "weblayout\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-web-layout ;\n"
           << "    muapit:value \"" << m.rtiWebLayout.toLower() << "\"^^xsd:string ;\n"
           << "    rdfs:label \"Web layout: " << wlLabel << " — " << sessionId << "\"@en .\n\n";
    }

    // Colour profile mode
    if (hasColorProfile) {
        ts << "rm-meas:" << measBase << "colorprofilemode\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-color-profile-mode ;\n"
           << "    muapit:value \"" << colorProfileModeStr << "\"^^xsd:string ;\n"
           << "    rdfs:label \"Colour profile mode: " << colorProfileModeStr << " — " << sessionId << "\"@en .\n\n";
    }

    // Openlime
    if (hasOpenlime) {
        ts << "rm-meas:" << measBase << "openlime\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-openlime ;\n"
           << "    muapit:value \"" << (openlime ? "true" : "false") << "\"^^xsd:boolean ;\n"
           << "    rdfs:label \"OpenLime viewer: " << (openlime ? "true" : "false") << " — " << sessionId << "\"@en .\n\n";
    }

    // Crop origin (x, y, angle — w/h already in schema:width/height)
    if (hasCropOrigin) {
        ts << "rm-meas:" << measBase << "croporigin\n"
           << "    a owl:NamedIndividual , a-dd:Measurement ;\n"
           << "    a-dd:hasMeasurementType rm-mtype:rti-crop-origin ;\n"
           << "    muapit:value \"" << cropOriginStr << "\"^^xsd:string ;\n"
           << "    rdfs:label \"Crop origin — " << sessionId << "\"@en .\n\n";
    }

    // ════════════════════════════════════════════════════════════════════════
    ts << "# ── E.4  New MeasurementType definitions (RTI-specific) ─────────────────\n\n";

    if (hasNPlanes || hasType) {
        ts << "rm-mtype:rti-nplanes\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"Number of RTI polynomial planes\"@en .\n\n";
    }

    if (hasType) {
        ts << "rm-mtype:rti-basis-type\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"RTI basis type\"@en .\n\n";
    }

    if (hasCS) {
        ts << "rm-mtype:rti-colorspace\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"RTI colour space encoding\"@en .\n\n";
    }

    if (hasPixelSize) {
        ts << "rm-mtype:pixel-size\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"Pixel size in millimetres\"@en .\n\n";
    }

    if (hasQuality) {
        ts << "rm-mtype:jpeg-quality\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"JPEG compression quality\"@en .\n\n";
    }

    if (hasWebLayout) {
        ts << "rm-mtype:rti-web-layout\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"RTI web output layout\"@en .\n\n";
    }

    if (hasColorProfile) {
        ts << "rm-mtype:rti-color-profile-mode\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"RTI colour profile mode\"@en .\n\n";
    }

    if (hasOpenlime) {
        ts << "rm-mtype:rti-openlime\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"OpenLime web viewer enabled\"@en .\n\n";
    }

    if (hasCropOrigin) {
        ts << "rm-mtype:rti-crop-origin\n"
           << "    a owl:NamedIndividual , a-dd:MeasurementType ;\n"
           << "    rdfs:label \"RTI output crop origin (x, y, angle)\"@en .\n\n";
    }

    // ════════════════════════════════════════════════════════════════════════
    //  SECTION E.5 — Processing software (a-dd:MeasurementType declares it)
    //
    //  RelightLab is the processing agent for this distribution.
    //  Typed as a-cd:PhotographicDocumentation + prov:SoftwareAgent so it
    //  integrates with the existing ArCo/PROV-O chain.
    // ════════════════════════════════════════════════════════════════════════
    ts << "# ── E.5  Processing software ─────────────────────────────────────────────\n"
       << "rm-equip:relightlab\n"
       << "    a owl:NamedIndividual , chs:Hardware ;\n"
       << "    dct:title       \"RelightLab\"^^xsd:string ;\n"
       << "    schema:version  \"" << QCoreApplication::applicationVersion() << "\"^^xsd:string ;\n"
       << "    foaf:page       <https://vcg.isti.cnr.it/relight/> ;\n"
       << "    rdfs:label      \"RelightLab "
       << QCoreApplication::applicationVersion() << "\"@en .\n\n";

    file.close();
    return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  §8  Provenance JSON writer  (public, automatic mode)
//
//  Writes an ontology-NEUTRAL provenance JSON sidecar next to info.json,
//  capturing the full RelightLab job record that only RelightLab knows at
//  export time. All ontology mapping is deferred to the external KG Builder,
//  so this output never changes when the ontology evolves.
//
//  taskInfo is the JSON RelightLab already emits via Task::info() on
//  ProcessQueue::finished — for an RtiTask: uuid, label, status, mime,
//  startedAt, output + parameters{ path, quality, crop, basis, colorSpace,
//  planeCount, format, webLayout, lossless, iiifManifest, openlime,
//  colorProfileMode }. Any new RTI parameter added upstream appears here
//  automatically. We add only what that record lacks: software name+version
//  and an export timestamp.
//
//  The plugin depends ONLY on this JSON, not on any RelightLab class, so it
//  installs unchanged across RelightLab versions. Does NOT duplicate the heavy
//  info.json payload (lights, materials) and does NOT read EXIF/XMP — the KG
//  Builder reads those from info.json and the source JPEGs directly.
// ═══════════════════════════════════════════════════════════════════════════

bool RdfExport::writeProvenanceJson(const QJsonObject &taskInfo,
                                    const QString     &outputPath,
                                    QString           &error)
{
    QJsonObject root = taskInfo;

    // exportTimestamp = when this sidecar was written (job start is startedAt).
    root["exportTimestamp"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);

    // Processing software — only RelightLab knows its own version.
    QJsonObject software;
    software["name"]    = QStringLiteral("RelightLab");
    software["version"] = QCoreApplication::applicationVersion();
    software["page"]    = QStringLiteral("https://vcg.isti.cnr.it/relight/");
    root["software"]    = software;

    QFile file(outputPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        error = "Cannot write to: " + outputPath;
        return false;
    }
    file.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
    file.close();
    return true;
}
