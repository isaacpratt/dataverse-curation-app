"""Curator-facing guidance for every check (dv-lfn) — the ported primers.

``GUIDANCE`` maps every check_id the engine can emit to a
``(rationale, remediation)`` pair: why the check matters for reuse, and
what to do about a finding. The text is written for curators, not
engineers — the DCN data curation primers are exactly this genre, and
this registry ports their pedagogy alongside the R inspectors' logic.

Surfaced by: the manifest/Auto-Checks tooltips (ui.checks_tree), the
Markdown report (engine.report_md), and the depositor-response
``{remediation}`` placeholder (response_draft).

The conformance test (curation/tests/test_guidance.py) statically scans
every check module for check-id literals and requires each one here, so
a new check cannot land without its guidance.
"""

from __future__ import annotations

from typing import Any

# check_id -> (rationale, remediation)
GUIDANCE: dict[str, tuple[str, str]] = {
    # -- format families (always-emit parents) ----------------------------
    "format.code": (
        "Code files are inspected so computational workflows can be rerun by reviewers.",
        "No action needed when it passes; address the code-specific findings otherwise.",
    ),
    "format.containers": (
        "Archives are tested so a corrupt upload never reaches users silently.",
        "When it fails, re-create the archive locally and upload it again.",
    ),
    "format.csv": (
        "CSV files are parsed end to end: structure, encoding, duplicate rows, and PII on a sample.",
        "Address the CSV-specific findings below.",
    ),
    "format.fastq": (
        "FASTQ reads are validated so sequencing data is usable without silent truncation.",
        "Address the FASTQ-specific findings below.",
    ),
    "format.gpkg": (
        "GeoPackage files are checked so spatial layers open with geometry and CRS intact.",
        "Address the GeoPackage-specific findings below.",
    ),
    "format.hdf5": (
        "HDF5 files are opened and their internal structure sanity-checked.",
        "Address the HDF5-specific findings below.",
    ),
    "format.images": (
        "Images are validated so figures open and render for every reader.",
        "Address the image-specific findings below.",
    ),
    "format.ipynb": (
        "Notebooks are inspected so the computational workflow they document can be followed.",
        "Address the notebook-specific findings below.",
    ),
    "format.json": (
        "JSON files are parsed to catch truncation and syntax drift.",
        "Address the JSON-specific findings below.",
    ),
    "format.netcdf": (
        "NetCDF files are opened and their metadata and data health inspected (CF-style checks).",
        "Address the NetCDF-specific findings below.",
    ),
    "format.pdf": (
        "PDFs are opened and checked for a usable text layer.",
        "Address the PDF-specific findings below.",
    ),
    "format.sas": (
        "SAS transport files are opened and their dictionaries and encodings read.",
        "Address the SAS-specific findings below.",
    ),
    "format.spss": (
        "SPSS files are opened and their dictionaries, labels, and encoding read.",
        "Address the SPSS-specific findings below.",
    ),
    "format.sqlite": (
        "SQLite databases are opened and their tables enumerated.",
        "Address the SQLite-specific findings below.",
    ),
    "format.stata": (
        "Stata files are opened and their dictionaries, labels, and encoding read.",
        "Address the Stata-specific findings below.",
    ),
    "format.text": (
        "Text files are scanned for encoding and control-character problems.",
        "Address the text-specific findings below.",
    ),
    "format.tiff": (
        "TIFF images are validated page by page.",
        "Address the TIFF-specific findings below.",
    ),
    "format.xlsx": (
        "Workbooks are parsed: sheets, hidden data, macros, and tabular structure.",
        "Address the workbook-specific findings below.",
    ),
    "format.xml": (
        "XML files are parsed for well-formedness.",
        "Address the XML-specific findings below.",
    ),
    "inventory.access": (
        "Access restrictions and embargoes from the inventory are surfaced for the review.",
        "Address the access findings below.",
    ),
    # -- code --------------------------------------------------------------
    "format.code.readable": (
        "Unreadable or mis-encoded scripts cannot be rerun by reviewers — the most common reason code deposits fail reuse.",
        "Re-save the file as UTF-8 (or ASCII) and avoid machine-generated dumps without a text layer.",
    ),
    "format.code.todo_markers": (
        "Leftover TODO/FIXME markers suggest unfinished work or local notes reviewers were not meant to see.",
        "Finish or remove the marked lines, or explain them in the README before release.",
    ),
    # -- containers ----------------------------------------------------------
    "format.containers.valid": (
        "A broken archive (bad CRC, truncated) loses data silently — the most damaging deposit defect.",
        "Re-extract and re-zip the archive locally, verify it opens, and replace the uploaded file.",
    ),
    "format.containers.encrypted": (
        "Password-protected archives cannot be opened by the repository, reviewers, or future users without the key.",
        "Remove the password and re-upload, or deposit the password through a restricted channel documented in the terms of access.",
    ),
    "format.containers.unsafe_entry": (
        "Absolute paths or parent-directory entries in an archive can escape the extraction folder (zip-slip) and are blocked by many systems.",
        "Re-pack the archive with relative paths only (files at or under the archive root).",
    ),
    # -- csv -----------------------------------------------------------------
    "format.csv.openable": (
        "A CSV that cannot be parsed cannot be ingested, previewed, or converted — it fails for every downstream user.",
        "Open the file in a spreadsheet or text editor, fix truncation or binary junk, and re-upload.",
    ),
    "format.csv.structure": (
        "Mixed delimiters or ragged rows break machine parsing — the most common cause of ingest failure and silent column misalignment.",
        "Re-export with a single consistent delimiter, quoting on, and one header row with identical column counts.",
    ),
    "format.csv.content": (
        "Duplicate rows and empty columns mislead analysis and inflate the file; reviewers flag them in almost every tabular deposit.",
        "Remove exact duplicate rows in a spreadsheet or script, and drop or document empty columns.",
    ),
    "format.csv.pii": (
        "Direct identifiers (emails, phone numbers, government IDs) in an open deposit are a privacy incident, not a formatting issue.",
        "Remove or de-identify the values (codes, ranges, or aggregate), or move the file behind restricted access with documented terms.",
    ),
    # -- fastq ---------------------------------------------------------------
    "format.fastq.valid": (
        "Malformed FASTQ records (unequal lengths, bad headers) break every downstream bioinformatics tool.",
        "Re-export the reads with a validated tool and replace the file.",
    ),
    "format.fastq.metadata": (
        "Missing per-read quality lines or identifiers make reads impossible to align or verify.",
        "Re-export with full quality lines and unique read identifiers.",
    ),
    # -- gpkg ----------------------------------------------------------------
    "format.gpkg.valid": (
        "An invalid GeoPackage cannot be opened by GIS software — the layer is effectively lost.",
        "Re-export from QGIS/ArcGIS as a new GeoPackage and verify it opens before re-uploading.",
    ),
    "format.gpkg.layers": (
        "Empty or unreadable layers waste deposit space and mislead reuse.",
        "Remove empty layers or repair them at the source, then re-export.",
    ),
    "format.gpkg.crs": (
        "Without a declared coordinate reference system, spatial data cannot be aligned with anything else.",
        "Assign the correct CRS (for example EPSG:4326) in your GIS and re-export.",
    ),
    # -- hdf5 ----------------------------------------------------------------
    "format.hdf5.openable": (
        "A corrupt HDF5 file silently loses every dataset inside it.",
        "Re-export the file (h5py/netCDF) and validate it before re-uploading.",
    ),
    "format.hdf5.external_links": (
        "External links point outside the file and break when the file moves — the linked data is lost to other users.",
        "Flatten external links into the file, or remove them and document the sources in the README.",
    ),
    # -- images / tiff ---------------------------------------------------------
    "format.images.valid": (
        "Corrupt or truncated images fail for every reader even when the thumbnail looks fine to the depositor.",
        "Re-export or re-save the image from the original and re-upload.",
    ),
    "format.tiff.valid": (
        "A corrupt multi-page TIFF loses pages silently.",
        "Re-export the TIFF from the imaging software and verify the page count before re-uploading.",
    ),
    # -- ipynb -----------------------------------------------------------------
    "format.ipynb.valid": (
        "A notebook that fails JSON parsing cannot be rendered on the dataset page or rerun.",
        "Re-save the notebook from Jupyter so the JSON is valid, then re-upload.",
    ),
    "format.ipynb.cells": (
        "Notebooks with missing outputs or broken cell structure cannot demonstrate the workflow they document.",
        "Restart and run all cells, then save so outputs are embedded.",
    ),
    "format.ipynb.executed": (
        "An unexecuted notebook shows no results — reviewers cannot verify the analysis ran.",
        "Run all cells (Restart & Run All) and save the executed notebook.",
    ),
    # -- json / xml ------------------------------------------------------------
    "format.json.valid": (
        "Invalid JSON cannot be consumed by any tool — typically a truncated or hand-edited file.",
        "Validate with a JSON linter, fix the syntax, and re-upload.",
    ),
    "format.xml.valid": (
        "Malformed XML cannot be parsed by any consumer — usually truncation or an unescaped character.",
        "Validate with an XML tool, fix the error, and re-upload.",
    ),
    # -- netcdf ------------------------------------------------------------------
    "format.netcdf.openable": (
        "A corrupt NetCDF file loses every variable it holds for downstream users.",
        "Re-export with ncdump/ncgen validation and replace the file.",
    ),
    "format.netcdf.metadata": (
        "Missing variable units, long names, or global attributes make the data uninterpretable outside the original team.",
        "Add units, long_name, and standard_name attributes plus a global title/history in the source script, then re-export.",
    ),
    "format.netcdf.data_health": (
        "Fill-value or range problems in the data grid silently corrupt analysis.",
        "Re-check the export pipeline's masking and fill values, then re-export.",
    ),
    "format.netcdf.spatial": (
        "Missing or inconsistent coordinate variables make the grid impossible to geolocate.",
        "Include monotonic lat/lon coordinate variables matching the data dimensions, then re-export.",
    ),
    # -- pdf -----------------------------------------------------------------
    "format.pdf.openable": (
        "A corrupt PDF cannot be opened by readers or preserved by the archive.",
        "Re-export or re-print the PDF from the source document and re-upload.",
    ),
    "format.pdf.text": (
        "Scanned-image PDFs have no text layer: they are invisible to search, screen readers, and text mining.",
        "Run OCR on the document (or deposit a born-digital export) so the text is selectable.",
    ),
    # -- sas / spss / stata -----------------------------------------------------
    "format.sas.openable": (
        "An unreadable SAS file cannot be converted or ingested by the repository.",
        "Re-export via PROC EXPORT or XPORT and verify with a fresh readstat pass.",
    ),
    "format.sas.dictionary": (
        "Missing variable metadata makes the dataset uninterpretable without the original codebook.",
        "Export variable labels and formats with the file (or add a codebook) so values are documented.",
    ),
    "format.sas.labels": (
        "Value labels carry the meaning of coded columns; without them, analysis misreads the codes.",
        "Attach value labels in the source dataset or document the code meanings in the README/data dictionary.",
    ),
    "format.sas.encoding": (
        "Wrong encoding garbles non-ASCII text (names, places) permanently.",
        "Re-export with the session encoding declared (UTF-8 recommended).",
    ),
    "format.sas.format_detected": (
        "The file did not match the expected SAS transport signature — it may be misnamed or corrupted in transfer.",
        "Confirm the export type (XPORT v5/v8/v9) matches the extension and re-upload.",
    ),
    "format.spss.openable": (
        "An unreadable SPSS file cannot be converted or ingested by the repository.",
        "Re-save the file in SPSS (or export to .sav via readstat) and verify it reopens.",
    ),
    "format.spss.dictionary": (
        "Missing variable metadata makes the dataset uninterpretable without the original codebook.",
        "Export variable labels with the file (or add a codebook) so values are documented.",
    ),
    "format.spss.labels": (
        "Value labels carry the meaning of coded columns; without them, analysis misreads the codes.",
        "Attach value labels in the source dataset or document the code meanings in the README/data dictionary.",
    ),
    "format.spss.encoding": (
        "Wrong encoding garbles non-ASCII text (names, places) permanently.",
        "Re-save with the session encoding declared (UTF-8 recommended).",
    ),
    "format.stata.openable": (
        "An unreadable Stata file cannot be converted or ingested by the repository.",
        "Re-save the file in Stata and verify it reopens before re-uploading.",
    ),
    "format.stata.dictionary": (
        "Missing variable metadata makes the dataset uninterpretable without the original codebook.",
        "Export variable labels with the file (or add a codebook) so values are documented.",
    ),
    "format.stata.labels": (
        "Value labels carry the meaning of coded columns; without them, analysis misreads the codes.",
        "Attach value labels in the source dataset or document the code meanings in the README/data dictionary.",
    ),
    "format.stata.encoding": (
        "Wrong encoding garbles non-ASCII text (names, places) permanently.",
        "Re-save with the session encoding declared (UTF-8 recommended).",
    ),
    "format.stata.pii": (
        "Direct identifiers in character columns of an open deposit are a privacy incident, not a formatting issue.",
        "De-identify the flagged columns or restrict the file; the check output lists the flagged values.",
    ),
    # -- sqlite --------------------------------------------------------------
    "format.sqlite.valid": (
        "A corrupt database loses all tables for every user.",
        "Run an integrity check at the source, re-export, and re-upload.",
    ),
    "format.sqlite.manifest": (
        "Users need to know which tables hold data before they can reuse the database.",
        "List the tables and row counts in the README (the check output can be pasted).",
    ),
    # -- text -----------------------------------------------------------------
    "format.text.readable": (
        "Text saved in a non-UTF-8 codepage garbles accents and symbols for every future reader.",
        "Re-save the file as UTF-8 (most editors have an encoding option) and re-upload.",
    ),
    "format.text.control_chars": (
        "Control characters (NUL, bell, escape) usually indicate binary contamination or a broken export.",
        "Re-export as clean text; if the content is binary, deposit it in its real format instead.",
    ),
    "format.text.line_endings": (
        "Mixed line endings break line-based tools and diffing, and bloat the file.",
        "Normalize the file to one line-ending style (LF or CRLF) with an editor or dos2unix and re-upload.",
    ),
    "format.text.pii": (
        "Direct identifiers (emails, phone numbers, government IDs) in an open deposit are a privacy incident, not a formatting issue.",
        "Remove or de-identify the flagged values (the check output lists them), or restrict the file.",
    ),
    # -- xlsx -----------------------------------------------------------------
    "format.xlsx.openable": (
        "A corrupt workbook cannot be opened by the repository's ingest or any reader.",
        "Open and re-save the workbook in Excel/LibreOffice, then re-upload.",
    ),
    "format.xlsx.sheets": (
        "Many or vaguely named sheets hide the real data table from reusers.",
        "Keep one sheet per table with a clear name; move notes to a README.",
    ),
    "format.xlsx.tabular": (
        "Merged cells, title rows above headers, or multiple tables per sheet break machine parsing.",
        "Restructure: one header row in row 1, one rectangular table per sheet, no merged cells.",
    ),
    "format.xlsx.hidden": (
        "Hidden sheets, rows, or columns carry content reviewers and reusers cannot see.",
        "Unhide and review the content; delete what is not needed and re-save.",
    ),
    "format.xlsx.macros": (
        "Macro-enabled workbooks are blocked by many systems and can carry active content.",
        "Save as .xlsx without macros; deposit the macro code separately as a code file if needed.",
    ),
    "format.xlsx.pii": (
        "Direct identifiers (emails, phone numbers, government IDs) in an open deposit are a privacy incident, not a formatting issue.",
        "Remove or de-identify the values (codes, ranges, or aggregate), or move the file behind restricted access with documented terms.",
    ),
    # -- secrets ----------------------------------------------------------------
    "format.secrets": (
        "API keys, tokens, and passwords in a deposit are a security incident: they must be treated as compromised.",
        "Revoke and rotate the credentials, remove them from the files (use environment variables), and re-upload.",
    ),
    # -- inventory ---------------------------------------------------------------
    "inventory.extensions": (
        "The extension census shows the deposit's shape; unrecognized formats need a preservation-risk review.",
        "Review the listed formats; convert to open formats where practical and document the rest.",
    ),
    "inventory.zero_byte": (
        "Zero-byte files are failed uploads or empty placeholders — they carry no data and fail ingest.",
        "Delete them or replace them with the real files; explain any intentional placeholder in the README.",
    ),
    "inventory.executables": (
        "Executables (.exe/.bat/…) are blocked by repositories and are a malware vector.",
        "Remove the executables, or deposit their source code as text instead.",
    ),
    "inventory.system_junk": (
        "OS junk (.DS_Store, Thumbs.db, __MACOSX) is noise that clutters the deposit and leaks local paths.",
        "Delete the junk files and re-upload a clean folder.",
    ),
    "inventory.restricted_files": (
        "Restricted files are invisible to the public; reuse depends on the terms of access being complete.",
        "Confirm the terms of access explain how to request the restricted files.",
    ),
    "inventory.embargoed_files": (
        "Embargoed files unlock on a date; the deposit page should explain when and why.",
        "State the embargo reason and end date in the dataset description or terms.",
    ),
    "metadata.var_coverage": (
        "Variable documentation is the layer reuse depends on: without labels, coded columns are uninterpretable outside the original team.",
        "Provide a codebook or label the variables at the source; the Draft data dictionary action exports a CSV the depositor can fill in.",
    ),
    "inventory.unchecked_types": (
        "Files nothing inspected have unknown risk: corrupt, empty or sensitive content can reach users unnoticed.",
        "Review the listed files manually (open them, check for personal data) and add a check or a note to the README.",
    ),
    "metadata.readme_sections": (
        "A README that skips overview, files, methods, missing-data codes or access leaves reusers guessing — the deposit is technically open but practically undocumented.",
        "Add the missing sections (each as a heading) so the README answers what the data is, what each file holds, how it was produced, how missing values are coded, and how it may be reused.",
    ),
}

# Human-facing names (dv-r0z, dv-dcd): the manifest, the Auto-Checks card,
# the Markdown report and docs/html/checks-reference.html all name a check
# through this map, so a user never reads ``format.csv.openable``. The
# conformance test requires one title per emitted id (and no stale ones);
# names stay in sentence case like every other label in the app.
TITLES: dict[str, str] = {
    # -- format families --------------------------------------------------
    "format.code": "Code Check",
    "format.code.readable": "Code Readable",
    "format.code.todo_markers": "TODO Markers",
    "format.containers": "Archive Check",
    "format.containers.valid": "Archive Readable",
    "format.containers.unsafe_entry": "Unsafe Archive Entry",
    "format.containers.encrypted": "Encrypted Archive Entry",
    "format.csv": "CSV Check",
    "format.csv.openable": "CSV Openable",
    "format.csv.structure": "CSV Structure",
    "format.csv.content": "CSV Content",
    "format.csv.pii": "CSV PII Scan",
    "format.fastq": "FASTQ Check",
    "format.fastq.valid": "FASTQ Validity",
    "format.fastq.metadata": "FASTQ Metadata",
    "format.gpkg": "GeoPackage Check",
    "format.gpkg.valid": "GeoPackage Validity",
    "format.gpkg.layers": "GeoPackage Layers",
    "format.gpkg.crs": "GeoPackage CRS",
    "format.hdf5": "HDF5 Check",
    "format.hdf5.openable": "HDF5 Openable",
    "format.hdf5.external_links": "HDF5 External Links",
    "format.images": "Image Check",
    "format.images.valid": "Image Validity",
    "format.ipynb": "Notebook Check",
    "format.ipynb.valid": "Notebook Validity",
    "format.ipynb.cells": "Notebook Cells",
    "format.ipynb.executed": "Notebook Executed",
    "format.json": "JSON Check",
    "format.json.valid": "JSON Validity",
    "format.netcdf": "NetCDF Check",
    "format.netcdf.openable": "NetCDF Openable",
    "format.netcdf.metadata": "NetCDF Metadata",
    "format.netcdf.data_health": "NetCDF Data Health",
    "format.netcdf.spatial": "NetCDF Spatial Coverage",
    "format.pdf": "PDF Check",
    "format.pdf.openable": "PDF Openable",
    "format.pdf.text": "PDF Text Layer",
    "format.sas": "SAS Check",
    "format.sas.openable": "SAS Openable",
    "format.sas.format_detected": "SAS File Format",
    "format.sas.encoding": "SAS Encoding",
    "format.sas.dictionary": "SAS Variable Dictionary",
    "format.sas.labels": "SAS Variable Labels",
    "format.secrets": "Secrets & Credentials",
    "format.spss": "SPSS Check",
    "format.spss.openable": "SPSS Openable",
    "format.spss.encoding": "SPSS Encoding",
    "format.spss.dictionary": "SPSS Variable Dictionary",
    "format.spss.labels": "SPSS Variable Labels",
    "format.sqlite": "SQLite Check",
    "format.sqlite.valid": "SQLite Validity",
    "format.sqlite.manifest": "SQLite Schema",
    "format.stata": "Stata Check",
    "format.stata.openable": "Stata Openable",
    "format.stata.encoding": "Stata Encoding",
    "format.stata.dictionary": "Stata Variable Dictionary",
    "format.stata.labels": "Stata Variable Labels",
    "format.stata.pii": "Stata PII Scan",
    "format.text": "Text Check",
    "format.text.readable": "Plain Text Readable",
    "format.text.line_endings": "Line Endings",
    "format.text.control_chars": "Control Characters",
    "format.text.pii": "Plain Text PII Scan",
    "format.tiff": "TIFF Check",
    "format.tiff.valid": "TIFF Validity",
    "format.xlsx": "Workbook Check",
    "format.xlsx.openable": "Workbook Opens",
    "format.xlsx.sheets": "Workbook Sheets",
    "format.xlsx.hidden": "Hidden Cells & Sheets",
    "format.xlsx.macros": "Macro Detection",
    "format.xlsx.tabular": "Tabular Structure",
    "format.xlsx.pii": "Workbook PII Scan",
    "format.xml": "XML Check",
    "format.xml.valid": "XML Validity",
    # -- dataset-level inventory ------------------------------------------
    "inventory.access": "Access Conditions",
    "inventory.extensions": "File Types",
    "inventory.zero_byte": "Zero-Byte Files",
    "inventory.executables": "Executable Files",
    "inventory.system_junk": "System Junk Files",
    "inventory.restricted_files": "Restricted Files",
    "inventory.embargoed_files": "Embargoed Files",
    "inventory.unchecked_types": "Unknown File Types",
    # -- dataset-level metadata -------------------------------------------
    "metadata.var_coverage": "Variable Documentation",
    "metadata.readme_sections": "README Sections",
}


def for_check(check_id: str) -> tuple[str, str]:
    """(rationale, remediation) for a check id; empty pair when unknown."""
    entry = GUIDANCE.get(str(check_id or ""))
    if not entry:
        return ("", "")
    return entry


def title_for(check_id: str) -> str:
    """Human-facing name for a check id; "" when the id is unknown."""
    return TITLES.get(str(check_id or "").strip(), "")


def for_result(result: Any) -> tuple[str, str]:
    """Guidance for a CheckResult: bespoke fields first, registry second."""
    rationale = str(getattr(result, "rationale", "") or "")
    remediation = str(getattr(result, "remediation", "") or "")
    if rationale and remediation:
        return (rationale, remediation)
    base_r, base_f = for_check(str(getattr(result, "check_id", "") or ""))
    return (rationale or base_r, remediation or base_f)
