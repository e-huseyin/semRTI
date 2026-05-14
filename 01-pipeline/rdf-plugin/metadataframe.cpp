/*
 * metadataframe.cpp  —  RDF / Linked-Data metadata editor for RelightLab
 *
 * All UI text follows British English conventions.
 * String handling uses UTF-8 throughout; non-Latin characters (e.g. ğ, ş, İ)
 * are preserved correctly in both the form display and the TTL output.
 */

#include "metadataframe.h"
#include "relightapp.h"
#include "mainwindow.h"
#include "rtiframe.h"
#include "rdfexport.h"

#include "../src/project.h"
#include "../src/rti/rtiparameters.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QGroupBox>
#include <QLineEdit>
#include <QLabel>
#include <QPushButton>
#include <QFileDialog>
#include <QMessageBox>
#include <QScrollArea>
#include <QShowEvent>

// ─── Internal helper ─────────────────────────────────────────────────────────

static QLineEdit *addRow(QFormLayout *form,
                         const QString &label,
                         const QString &placeholder = {})
{
    auto *le = new QLineEdit;
    le->setPlaceholderText(placeholder);
    form->addRow(label, le);
    return le;
}

static QLabel *addDisplay(QFormLayout *form, const QString &label)
{
    auto *lbl = new QLabel("—");
    lbl->setWordWrap(true);
    form->addRow(label, lbl);
    return lbl;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Constructor
// ─────────────────────────────────────────────────────────────────────────────

MetadataFrame::MetadataFrame(QWidget *parent) : QFrame(parent)
{
    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    auto *inner = new QWidget;
    scroll->setWidget(inner);

    auto *outerLayout = new QVBoxLayout(this);
    outerLayout->setContentsMargins(0, 0, 0, 0);
    outerLayout->addWidget(scroll);

    auto *content = new QVBoxLayout(inner);
    content->addWidget(new QLabel("<h2>RDF / Linked-Data Export</h2>"));
    content->addWidget(new QLabel(
        "Review and complete the fields below, then click <b>Export TTL</b> to write "
        "a W3C Turtle sidecar file describing this RTI dataset.<br>"
        "Fields marked <b>*</b> are auto-detected from the embedded EXIF and XMP "
        "metadata of the first source image. Editable fields are pre-filled from XMP "
        "when empty — you may override any value before exporting."));
    content->addSpacing(8);

    // ── Dataset Identification ────────────────────────────────────────────────
    {
        auto *box  = new QGroupBox("Dataset Identification");
        auto *form = new QFormLayout(box);

        le_datasetId = addRow(form, "Dataset ID:",
            "e.g. Project_2026_A  (from dc:title)");
        le_featureId = addRow(form, "Object / Feature ID:",
            "e.g. F11  (from xmp:Nickname)");
        le_siteName  = addRow(form, "Site name:",
            "e.g. Rupe Magna  (from IPTC Location / City)");

        content->addWidget(box);
    }

    // ── Rights and Authority ─────────────────────────────────────────────────
    {
        auto *box  = new QGroupBox("Rights and Authority");
        auto *form = new QFormLayout(box);

        le_artistName  = addRow(form, "Author name:",
            "e.g. Jane Doe  (from dc:creator / EXIF Artist)");
        le_artistRole  = addRow(form, "Author role:",
            "e.g. Researcher  (from IPTC AuthorsPosition)");
        le_artistEmail = addRow(form, "Author e-mail:",
            "e.g. researcher@institution.ac.uk  (from IPTC CiEmailWork)");
        le_orcid       = addRow(form, "ORCID URL:",
            "https://orcid.org/0000-0000-0000-0000  (from IPTC CreatorWorkURL)");
        le_institution = addRow(form, "Institution:",
            "e.g. University of Example  (from photoshop:Credit)");
        le_copyright   = addRow(form, "Copyright:",
            "e.g. © 2025 Jane Doe  (from dc:rights)");
        le_licenseUrl  = addRow(form, "Licence URL:",
            "https://creativecommons.org/licenses/by/4.0/  (from xmpRights:WebStatement)");
        le_kgBaseUri   = addRow(form, "KG Base URI:",
            "https://example.org/rti/kg/");

        content->addWidget(box);
    }

    // ── Location / GPS ───────────────────────────────────────────────────────
    {
        auto *box  = new QGroupBox(
            "Location / GPS  (auto-detected from EXIF; enter manually if absent)");
        auto *form = new QFormLayout(box);

        le_gpsLat = addRow(form, "Latitude (°N):",  "e.g. 46.028500");
        le_gpsLon = addRow(form, "Longitude (°E):", "e.g. 10.355400");
        le_gpsAlt = addRow(form, "Altitude (m):",   "e.g. 350");

        lbl_city     = addDisplay(form, "City *:");
        lbl_province = addDisplay(form, "Province/State *:");
        lbl_country  = addDisplay(form, "Country *:");

        content->addWidget(box);
    }

    // ── Auto-detected from EXIF / XMP ────────────────────────────────────────
    {
        auto *box  = new QGroupBox("Auto-detected from EXIF / XMP  (read-only)");
        auto *form = new QFormLayout(box);

        lbl_camera       = addDisplay(form, "Camera *:");
        lbl_cameraSerial = addDisplay(form, "Camera serial *:");
        lbl_lens         = addDisplay(form, "Lens *:");
        lbl_exposure     = addDisplay(form, "Exposure *:");
        lbl_date         = addDisplay(form, "Date *:");
        lbl_rawSource    = addDisplay(form, "RAW source *:");
        lbl_dome         = addDisplay(form, "Dome / Lights *:");

        auto *refreshBtn = new QPushButton("Refresh from Image Metadata");
        refreshBtn->setToolTip(
            "Reads EXIF and XMP from the first source image and updates all fields.");
        form->addRow("", refreshBtn);
        connect(refreshBtn, &QPushButton::clicked,
                this, &MetadataFrame::refreshFromImage);

        content->addWidget(box);
    }

    // ── Output Path ───────────────────────────────────────────────────────────
    {
        auto *box  = new QGroupBox("Output");
        auto *hbox = new QHBoxLayout(box);

        le_outputPath = new QLineEdit;
        le_outputPath->setPlaceholderText("/path/to/output/dataset.ttl");

        auto *browseBtn = new QPushButton("Browse…");
        connect(browseBtn, &QPushButton::clicked,
                this, &MetadataFrame::chooseOutputPath);

        hbox->addWidget(le_outputPath, 1);
        hbox->addWidget(browseBtn);
        content->addWidget(box);
    }

    // ── Export Button ─────────────────────────────────────────────────────────
    {
        auto *row       = new QHBoxLayout;
        auto *exportBtn = new QPushButton("Export TTL");
        exportBtn->setProperty("class", "large");
        exportBtn->setMinimumWidth(200);
        exportBtn->setToolTip("Write a W3C Turtle (.ttl) file to the selected output path.");
        connect(exportBtn, &QPushButton::clicked,
                this, &MetadataFrame::exportTtl);
        row->addStretch(1);
        row->addWidget(exportBtn);
        row->addStretch(1);
        content->addLayout(row);
    }

    content->addStretch();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Lifecycle
// ─────────────────────────────────────────────────────────────────────────────

void MetadataFrame::clear()
{
    le_datasetId->clear();
    le_featureId->clear();
    le_siteName->clear();
    le_artistName->clear();
    le_artistRole->clear();
    le_artistEmail->clear();
    le_orcid->clear();
    le_institution->clear();
    le_copyright->clear();
    le_licenseUrl->clear();
    le_kgBaseUri->clear();
    le_gpsLat->clear();
    le_gpsLon->clear();
    le_gpsAlt->clear();
    le_outputPath->clear();

    lbl_camera->setText("—");
    lbl_cameraSerial->setText("—");
    lbl_lens->setText("—");
    lbl_exposure->setText("—");
    lbl_date->setText("—");
    lbl_city->setText("—");
    lbl_province->setText("—");
    lbl_country->setText("—");
    lbl_rawSource->setText("—");
    lbl_dome->setText("—");

    currentMeta = RdfMetadata{};
}

void MetadataFrame::init()
{
    refreshFromImage();
}

void MetadataFrame::showEvent(QShowEvent *event)
{
    QFrame::showEvent(event);
    if (!qRelightApp->project().images.empty())
        refreshFromImage();
    if (le_outputPath->text().isEmpty())
        le_outputPath->setText(suggestOutputPath());
}

// ─────────────────────────────────────────────────────────────────────────────
//  Slots
// ─────────────────────────────────────────────────────────────────────────────

void MetadataFrame::refreshFromImage()
{
    const Project &project = qRelightApp->project();
    currentMeta = RdfExport::readFromProject(project);
    applyMetaToForm(currentMeta);
}

QString MetadataFrame::suggestOutputPath() const
{
    QString rtiOutputPath;
    if (qRelightApp->mainwindow && qRelightApp->mainwindow->rtiFrame())
        rtiOutputPath = qRelightApp->mainwindow->rtiFrame()->parameters.path;

    if (!rtiOutputPath.isEmpty()) {
        const QString folderName = QDir(rtiOutputPath).dirName();
        const QString prefix     = le_featureId->text().trimmed()
                                 + le_datasetId->text().trimmed();
        const QString fileName   = (prefix.isEmpty() ? folderName
                                                      : prefix + "-" + folderName)
                                 + ".ttl";
        return QDir(rtiOutputPath).filePath(fileName);
    }

    const Project &project = qRelightApp->project();
    const QString name = (le_datasetId->text().isEmpty() ? "rti_dataset"
                                                         : le_datasetId->text())
                       + ".ttl";
    return project.dir.filePath(name);
}

void MetadataFrame::chooseOutputPath()
{
    const QString path = QFileDialog::getSaveFileName(
        this,
        "Save Turtle RDF file",
        suggestOutputPath(),
        "Turtle RDF (*.ttl)");

    if (!path.isEmpty())
        le_outputPath->setText(path);
}

void MetadataFrame::exportTtl()
{
    if (le_outputPath->text().trimmed().isEmpty()) {
        QMessageBox::warning(this,
            "Output path missing",
            "Please choose an output path for the Turtle RDF file.");
        return;
    }

    const Project &project = qRelightApp->project();
    const RdfMetadata meta = collectMeta();

    // Read current RTI parameters from RtiFrame so that the manual export
    // contains the same processing metadata as the automatic sidecar.
    const RtiParameters *params = nullptr;
    RtiParameters rtiParams;
    if (qRelightApp->mainwindow && qRelightApp->mainwindow->rtiFrame()) {
        rtiParams = qRelightApp->mainwindow->rtiFrame()->parameters;
        params    = &rtiParams;
    }

    QString error;
    if (!RdfExport::write(project, params, meta, le_outputPath->text(), error)) {
        QMessageBox::critical(this, "Export failed", error);
        return;
    }

    QMessageBox::information(this,
        "Export successful",
        "Turtle RDF file written to:\n" + le_outputPath->text());
}

// ─────────────────────────────────────────────────────────────────────────────
//  applyMetaToForm
//
//  Transfers RdfMetadata into the form widgets.
//  Editable fields are filled from XMP/EXIF only when currently empty.
//  Read-only display labels are always refreshed.
// ─────────────────────────────────────────────────────────────────────────────

void MetadataFrame::applyMetaToForm(const RdfMetadata &meta)
{
    // ── Editable fields — filled only when empty ─────────────────────────────

    if (le_artistName->text().isEmpty()  && !meta.artistName.isEmpty())
        le_artistName->setText(meta.artistName);
    if (le_artistRole->text().isEmpty()  && !meta.artistRole.isEmpty())
        le_artistRole->setText(meta.artistRole);
    if (le_artistEmail->text().isEmpty() && !meta.artistEmail.isEmpty())
        le_artistEmail->setText(meta.artistEmail);
    if (le_orcid->text().isEmpty()       && !meta.orcid.isEmpty())
        le_orcid->setText(meta.orcid);
    if (le_institution->text().isEmpty() && !meta.institution.isEmpty())
        le_institution->setText(meta.institution);
    if (le_copyright->text().isEmpty()   && !meta.copyright.isEmpty())
        le_copyright->setText(meta.copyright);
    if (le_licenseUrl->text().isEmpty()  && !meta.licenseUrl.isEmpty())
        le_licenseUrl->setText(meta.licenseUrl);
    if (le_kgBaseUri->text().isEmpty()   && !meta.kgBaseUri.isEmpty())
        le_kgBaseUri->setText(meta.kgBaseUri);

    if (le_datasetId->text().isEmpty() && !meta.datasetId.isEmpty())
        le_datasetId->setText(meta.datasetId);
    if (le_featureId->text().isEmpty() && !meta.featureId.isEmpty())
        le_featureId->setText(meta.featureId);
    if (le_siteName->text().isEmpty()  && !meta.siteName.isEmpty())
        le_siteName->setText(meta.siteName);

    // GPS — fill editable fields from EXIF when available and fields are empty
    if (meta.hasGps) {
        if (le_gpsLat->text().isEmpty())
            le_gpsLat->setText(QString::number(meta.gpsLat, 'f', 6));
        if (le_gpsLon->text().isEmpty())
            le_gpsLon->setText(QString::number(meta.gpsLon, 'f', 6));
        if (le_gpsAlt->text().isEmpty() && meta.gpsAlt != 0.0)
            le_gpsAlt->setText(QString::number(meta.gpsAlt, 'f', 1));
    }

    // ── Read-only display labels — always refreshed ───────────────────────────

    // Camera
    const QString camera = (meta.cameraMake + " " + meta.cameraModel).trimmed();
    lbl_camera->setText(camera.isEmpty() ? "—" : camera);
    lbl_cameraSerial->setText(meta.cameraSerial.isEmpty() ? "—" : meta.cameraSerial);

    // Lens
    QString lensText = meta.lensModel;
    if (!meta.lensSerial.isEmpty()) lensText += "  (S/N: " + meta.lensSerial + ")";
    lbl_lens->setText(lensText.isEmpty() ? "—" : lensText);

    // Exposure
    if (meta.iso > 0 || meta.fnumber > 0
        || meta.exposureTime > 0 || meta.focalLength > 0)
    {
        QStringList parts;
        if (meta.iso > 0)
            parts << QString("ISO %1").arg(meta.iso);
        if (meta.fnumber > 0)
            parts << QString("f/%1").arg(meta.fnumber, 0, 'f', 1);
        if (meta.exposureTime > 0) {
            if (meta.exposureTime < 1.0)
                parts << QString("1/%1 s").arg(qRound(1.0 / meta.exposureTime));
            else
                parts << QString("%1 s").arg(meta.exposureTime, 0, 'f', 1);
        }
        if (meta.focalLength > 0)
            parts << QString("%1 mm").arg(meta.focalLength, 0, 'f', 1);
        lbl_exposure->setText(parts.join("  ·  "));
    } else {
        lbl_exposure->setText("—");
    }

    // Acquisition date
    lbl_date->setText(meta.acquisitionDate.isValid()
        ? meta.acquisitionDate.toString("yyyy-MM-dd  HH:mm:ss")
        : "—");

    // Textual location (read-only display — the fields themselves are in the GPS group)
    lbl_city->setText(meta.city.isEmpty()     ? "—" : meta.city);
    lbl_province->setText(meta.province.isEmpty() ? "—" : meta.province);
    lbl_country->setText(meta.country.isEmpty()  ? "—" : meta.country);

    // RAW source file
    lbl_rawSource->setText(meta.rawSourceFile.isEmpty() ? "—" : meta.rawSourceFile);

    // Dome
    const Project &project = qRelightApp->project();
    QStringList domeParts;
    if (!project.dome.label.isEmpty())
        domeParts << project.dome.label;
    if (project.dome.directions.size() > 0)
        domeParts << QString::number(project.dome.directions.size()) + " lights";
    if (project.dome.domeDiameter > 0)
        domeParts << QString("⌀ %1 mm").arg(project.dome.domeDiameter, 0, 'f', 0);
    lbl_dome->setText(domeParts.isEmpty() ? "—" : domeParts.join("  |  "));
}

// ─────────────────────────────────────────────────────────────────────────────
//  collectMeta
//
//  Assembles the final RdfMetadata from the form, using currentMeta as the
//  base so that EXIF-only fields (camera serial, lens, checksum, etc.) that
//  are not shown as editable inputs are still included in the export.
// ─────────────────────────────────────────────────────────────────────────────

RdfMetadata MetadataFrame::collectMeta() const
{
    RdfMetadata m = currentMeta;

    m.datasetId   = le_datasetId->text().trimmed();
    m.featureId   = le_featureId->text().trimmed();
    m.siteName    = le_siteName->text().trimmed();
    m.artistName  = le_artistName->text().trimmed();
    m.artistRole  = le_artistRole->text().trimmed();
    m.artistEmail = le_artistEmail->text().trimmed();
    m.orcid       = le_orcid->text().trimmed();
    m.institution = le_institution->text().trimmed();
    m.copyright   = le_copyright->text().trimmed();
    m.licenseUrl  = le_licenseUrl->text().trimmed();
    m.kgBaseUri   = le_kgBaseUri->text().trimmed();

    // GPS from editable fields — override EXIF values if the user has
    // typed coordinates (useful when the source images lack GPS metadata).
    bool latOk = false, lonOk = false;
    const double lat = le_gpsLat->text().trimmed().toDouble(&latOk);
    const double lon = le_gpsLon->text().trimmed().toDouble(&lonOk);
    if (latOk && lonOk) {
        m.gpsLat = lat;
        m.gpsLon = lon;
        m.gpsAlt = le_gpsAlt->text().trimmed().toDouble();
        m.hasGps = true;
    }

    return m;
}
