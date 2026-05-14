/*
 * rdfexport.h  —  RDF/Turtle export for RelightLab (Sem-RTI pipeline)
 *
 * Generates a W3C Turtle sidecar file describing the RTI processing output
 * (Section E) using the same ontologies and namespace as the Sem-RTI
 * SPARQL Anything pipeline:
 *
 *   ArCo   https://w3id.org/arco
 *   CHS-ODP  http://www.ontologydesignpatterns.org/cp/owl/culturalheritagesurvey.owl#
 *   muapit   https://w3id.org/italia/onto/MU/
 *   tiapit   https://w3id.org/italia/onto/TI/
 *   roapit   https://w3id.org/italia/onto/RO/
 *   DCAT 3   https://www.w3.org/ns/dcat#
 *   DCT      http://purl.org/dc/terms/
 *
 * The output TTL describes the RTI distribution produced by RelightLab and
 * links it to the existing pipeline dataset (rm-data:{sessionId}).
 * It is designed to be merged with rupe-magna-complete.ttl.
 *
 * Usage
 * ─────
 *   Approach A — automatic sidecar: called from RtiFrame after export.
 *   Approach B — manual form:       called from MetadataFrame on demand.
 */

#ifndef RDFEXPORT_H
#define RDFEXPORT_H

#include <QString>
#include <QDateTime>

class Project;
class RtiParameters;

// ─────────────────────────────────────────────────────────────────────────────
//  RdfMetadata  —  flat metadata bag consumed by RdfExport::write()
//
//  [user]  set interactively in MetadataFrame
//  [auto]  populated automatically by readFromProject() / readFromInfoJson()
// ─────────────────────────────────────────────────────────────────────────────
struct RdfMetadata {

    // ── [user] Dataset identification ────────────────────────────────────────
    // Parsed automatically from dc:title bracket notation
    // e.g. "Rupe Magna - [F09] - [RTI-35]" → siteName="Rupe Magna",
    //                                         featureId="F09", datasetId="RTI-35"
    QString datasetId;   // session ID,  e.g. "RTI-35"
    QString featureId;   // figure ID,   e.g. "F09"
    QString siteName;    // site name,   e.g. "Rupe Magna"

    // ── [user] Rights and authority ──────────────────────────────────────────
    QString orcid;       // ORCID URL, e.g. "https://orcid.org/0000-0002-2965-0918"
    QString institution; // e.g. "Alma Mater Studiorum – Università di Bologna"
    QString licenseUrl;  // defaults to CC BY 4.0
    QString kgBaseUri;   // KG base, e.g. "https://w3id.org/rupemagna/resource/"

    // ── [auto] From XMP (UTF-8) ───────────────────────────────────────────────
    QString artistName;  // dc:creator
    QString artistRole;  // Iptc4xmpCore:AuthorsPosition
    QString artistEmail; // Iptc4xmpCore:CiEmailWork
    QString copyright;   // dc:rights

    // ── [auto] From EXIF (binary) ─────────────────────────────────────────────
    QString cameraMake;
    QString cameraModel;
    QString cameraSerial;
    QString lensModel;
    QString lensSerial;
    double  focalLength  = 0.0;  // mm
    int     iso          = 0;
    double  fnumber      = 0.0;
    double  exposureTime = 0.0;  // seconds
    QDateTime acquisitionDate;
    double  gpsLat = 0.0;
    double  gpsLon = 0.0;
    double  gpsAlt = 0.0;
    bool    hasGps = false;

    // ── [auto] From Project object ────────────────────────────────────────────
    int     imageCount          = 0;    // non-skipped source images
    QString rawSourceFile;              // Iptc4xmpExt:OriginalFileName (e.g. "DSCF6224.RAF")
    QString imageChecksumSha256;        // SHA-256 hex digest of first source JPEG

    // ── [auto] From XMP photoshop namespace ──────────────────────────────────
    QString city;        // photoshop:City
    QString province;    // photoshop:State
    QString country;     // photoshop:Country

    // ── [auto] From info.json (RTI processing output) ─────────────────────────
    // Populated by readFromInfoJson() when params->path contains info.json.
    int     rtiWidth        = 0;
    int     rtiHeight       = 0;
    double  pixelSizeInMM   = 0.0;
    QString rtiType;         // "ptm", "hsh", "rbf" ...
    QString rtiColorspace;   // "rgb", "lrgb", "ycc" ...
    int     rtiNPlanes      = 0;
    int     rtiQuality      = 0;
    QString rtiColorProfile; // "sRGB"
    QString rtiWebLayout;   // "plain", "deepzoom", "tarzoom", "itarzoom" (empty if RTI format)
    bool    hasRtiOutput    = false;
};

// ─────────────────────────────────────────────────────────────────────────────
//  RdfExport  —  static utility class
// ─────────────────────────────────────────────────────────────────────────────
class RdfExport {
public:
    // Populate RdfMetadata from the first non-skipped source image.
    // Reads EXIF (binary) for camera/GPS/exposure, then XMP (UTF-8 XML) for
    // textual fields (author, title, ORCID, location, licence).
    static RdfMetadata readFromProject(const Project &project);

    // Populate RTI output fields from info.json in outputDir.
    // Safe to call when outputDir is empty or info.json does not yet exist.
    static void readFromInfoJson(const QString &outputDir, RdfMetadata &meta);

    // Write a Turtle sidecar file to outputPath.
    // params may be nullptr (manual export before RTI processing).
    // Returns false and sets error on I/O failure.
    static bool write(const Project       &project,
                      const RtiParameters *params,
                      const RdfMetadata   &meta,
                      const QString       &outputPath,
                      QString             &error);

private:
    static QString slugify(const QString &s);
    static QString rtiTypeLabel(const QString &type);
    static QString colorspaceLabel(const QString &cs);
    static QString colorProfileModeLabel(int mode);
};

#endif // RDFEXPORT_H
