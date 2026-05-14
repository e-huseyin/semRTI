/*
 * metadataframe.h  —  RDF / Linked-Data metadata editor for RelightLab
 *
 * Displays and edits all EXIF/XMP metadata available in the source images
 * before exporting a W3C Turtle (.ttl) sidecar file aligned with the ArCo
 * cultural heritage ontology.
 *
 * Layout
 * ──────
 *  § Dataset Identification   (editable)
 *  § Rights and Authority     (editable — auto-populated from XMP)
 *  § Location / GPS           (editable — auto-populated from EXIF GPS)
 *  § Auto-detected from EXIF/XMP  (read-only display)
 *  § Output path + Export button
 */

#ifndef METADATAFRAME_H
#define METADATAFRAME_H

#include <QFrame>
#include "rdfexport.h"

class QLineEdit;
class QLabel;
class QPushButton;

class MetadataFrame : public QFrame {
    Q_OBJECT

public:
    explicit MetadataFrame(QWidget *parent = nullptr);

    // Called by MainWindow on project load / close.
    void init();
    void clear();

protected:
    // Auto-refresh when the tab becomes visible.
    void showEvent(QShowEvent *event) override;

private slots:
    void refreshFromImage();   // reads EXIF + XMP, populates form fields
    void chooseOutputPath();
    void exportTtl();

private:
    // ── Dataset identification ───────────────────────────────────────────────
    QLineEdit *le_datasetId  = nullptr;   // dc:title
    QLineEdit *le_featureId  = nullptr;   // xmp:Nickname
    QLineEdit *le_siteName   = nullptr;   // Iptc4xmpCore:Location / photoshop:City

    // ── Rights and authority ─────────────────────────────────────────────────
    QLineEdit *le_artistName  = nullptr;  // dc:creator
    QLineEdit *le_artistRole  = nullptr;  // Iptc4xmpCore:AuthorsPosition
    QLineEdit *le_artistEmail = nullptr;  // Iptc4xmpCore:CiEmailWork
    QLineEdit *le_orcid       = nullptr;  // Iptc4xmpCore:CreatorWorkURL
    QLineEdit *le_institution = nullptr;  // photoshop:Credit
    QLineEdit *le_copyright   = nullptr;  // dc:rights
    QLineEdit *le_licenseUrl  = nullptr;  // xmpRights:WebStatement
    QLineEdit *le_kgBaseUri   = nullptr;  // user-defined KG namespace

    // ── Location / GPS (editable — auto-populated from EXIF or entered manually)
    QLineEdit *le_gpsLat      = nullptr;  // decimal degrees N
    QLineEdit *le_gpsLon      = nullptr;  // decimal degrees E
    QLineEdit *le_gpsAlt      = nullptr;  // metres a.s.l.

    // ── Auto-detected display labels (read-only) ─────────────────────────────
    QLabel *lbl_camera        = nullptr;  // Make + Model
    QLabel *lbl_cameraSerial  = nullptr;  // Camera serial number
    QLabel *lbl_lens          = nullptr;  // Lens model + serial
    QLabel *lbl_exposure      = nullptr;  // ISO / f/ / shutter / focal length
    QLabel *lbl_date          = nullptr;  // DateTimeOriginal
    QLabel *lbl_city          = nullptr;  // photoshop:City (read-only display)
    QLabel *lbl_province      = nullptr;  // photoshop:State
    QLabel *lbl_country       = nullptr;  // photoshop:Country
    QLabel *lbl_rawSource     = nullptr;  // Iptc4xmpExt:OriginalFileName
    QLabel *lbl_dome          = nullptr;  // label / LED count / diameter

    // ── Output ───────────────────────────────────────────────────────────────
    QLineEdit *le_outputPath  = nullptr;

    // Last metadata read from EXIF + XMP (base for collectMeta())
    RdfMetadata currentMeta;

    // Transfers metadata into the display / editable widgets.
    // Editable fields are only overwritten when currently empty.
    void applyMetaToForm(const RdfMetadata &meta);

    // Collects current form state into an RdfMetadata ready for write().
    RdfMetadata collectMeta() const;

    // Returns the suggested TTL output path based on the current RTI output
    // folder: {rtiOutputDir}/{featureId}{sessionId}-{folderName}.ttl
    // Falls back to project dir + datasetId when no RTI output path is set.
    QString suggestOutputPath() const;
};

#endif // METADATAFRAME_H
