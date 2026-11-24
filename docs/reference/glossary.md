---
page_type: reference
tgdp_template: Glossary     # Reference | Glossary
audience: all                # curator | developer | contributor | all
---
# Glossary

Definitions of the Dataverse, curation and app terms used across this documentation.

## Dataverse and curation terms

| Term | Definition |
| --- | --- |
| Dataverse | The repository platform the app works with (Native/Search API only). A Dataverse instance is a specific deployment, e.g. the Borealis demo at `https://demo.borealisdata.ca`. See [Dataverse API reference](dataverse-api.md) |
| dataset | A deposited collection of files plus its metadata, identified by a persistent ID. The unit the app reviews and reports on |
| draft | An unpublished, editable version of a dataset. Search with a token returns drafts; without a token only published versions are visible. See [Dataverse API reference](dataverse-api.md#review-state-discovery) |
| persistent ID / DOI | A permanent identifier for a dataset, e.g. `doi:10.5072/FK2/EXAMPLE`. Passed to headless runs as `--persistent-id` and recorded in the [DatasetReport](report-contract.md) |
| curation label | A collection-specific status label assigned to a dataset under curation (e.g. "reviewed", "published"). Allowed labels come from `allowedCurationLabels`; the bulk-first workflow is described in [Dataverse API reference](dataverse-api.md#curation-labels) |
| collection | A named subset of a Dataverse instance, identified by an alias and used as the discovery `subtree`. An empty alias or `:root`/`root` means the whole repository |
| deposit | The whole submission handed to the repository: files, citation metadata, access terms and associated review outputs |
| depositor | The researcher or data owner who submitted the deposit and to whom response drafts are addressed |
| curator | The person reviewing a deposit — running checks, assessing metadata completeness and deciding the disposition |
| review ruleset | A versioned set of field rules (v2 in `requirements_profiles.json`) governing metadata completeness. The built-in profiles are McMaster and Minimal; field rules can use the [`looks_correct` handler](entry-checks.md) |
| metadata block | A Dataverse grouping of metadata fields (e.g. Citation, DDI). Blocks are discovered via the instance's metadatablocks cache |
| citation block | The core descriptive metadata of a dataset — title, authors, description, time period, etc. — read from the dataset endpoint and evaluated by the metadata completeness checks |
| DDI | Data Documentation Initiative — the XML metadata standard Dataverse uses for variable-level documentation. The app reads per-file DDI at `/api/access/datafile/:id/metadata/ddi` for the variable-coverage check and dictionary draft |
| tabular ingest | Dataverse's conversion of an uploaded tabular file (e.g. `.sav`) into a usable tabular form. The app prefers the original file for checking and reads ingest state from the `ingestStatus` field of the version payload |
| `.tab` | A server-regenerated tabular derivative file. Download verification compares its UNF rather than hashing byte-exact; original-format downloads remove `.tab` files |
| guestbook | A per-dataset form a depositor may require before download. The app renders it in the approval dialog, POSTs the answers and streams the returned signed URL. See [Dataverse API reference](dataverse-api.md#download-flow-approval-gated) |
| embargo | A time restriction on a file: it is released on a stated date. Embargoed files are surfaced by `inventory.embargoed_files` with their date and terms of access |
| restricted file | A file invisible to the public, accessible only under stated terms. Restricted files are surfaced by `inventory.restricted_files` in the DatasetReport |
| disposition | A curator's recorded decision on a finding — e.g. `acknowledged` or `wontfix`. Dispositions discount or exclude findings from the response draft and readiness verdict |
| curation record | A local audit bundle (`curation-record/<YYYYMMDD-HHMMSS>/`) combining the checks report, depositor response, timeline, dispositions, questionnaire, decision + label, and a `sha256sums.txt` manifest bound by `index.json` |

## Files, checks and reports

| Term | Definition |
| --- | --- |
| staged / original file | A file downloaded into the workspace and prepared for checking. "Original" is the source-format file fetched via `?format=original` (as opposed to a `.tab` derivative); staging unzips to `files.new/` then swaps atomically |
| check ID | A stable dotted identifier for a check, e.g. `format.csv.structure` or `inventory.extensions`. The registry has 24 family keys; reports include more specific IDs — see the [Check ID index](checks.md#check-id-index) |
| check scope | The declared `dataset` or `file` scope of a check. It decides whether the finding lands in `dataset_checks` or in a file entry's `checks` — never the file extensions a check reads |
| DatasetReport | The single JSON structure (`engine/report.py`) shared by engine, GUI and headless export. Holds `dataset_checks` plus per-file `files[].checks`; see [Report contract](report-contract.md) |
| headless mode | The `--headless` CLI path: runs checks on a local staged directory, writes a report, uses no Qt/config/network and exits 0 (clean), 1 (error-level findings) or 2 (usage/IO failure). See [Command-line reference](cli.md) |
| workspace | The folder for staged downloads and caches (`app.workspace`, default `~/Documents/curation-workspace`). Overridden by `DATAVERSE_WORKSPACE`. See [Configuration reference](configuration.md#on-disk-artefacts) |
| keyring | The OS credential store (Windows Credential Manager on Windows) used by default to hold the API token, keyed by base URL. `api_token_source` names it; plaintext in `config.json` is the fallback |
| Zensical | The static site generator that builds this documentation site from the Markdown tree in `docs/` (configured by `zensical.toml`) |
| Diátaxis | The documentation framework organising content into four quadrants: tutorials, how-to guides, reference and explanation. This page set uses its Reference/Glossary template structures |
| UNF | Universal Numeric Fingerprint — Dataverse's content-based signature for tabular data. Because `.tab` derivatives are regenerated by the server, download verification reports the UNF for manual comparison instead of expecting a byte-exact checksum |
| manifest / manifest tree | The File checks view of every staged file as folder › file › check, built from `files[].checks` in the [DatasetReport](report-contract.md) |
| family ID | A registry key such as `format.csv`. Each module always emits its family check and may emit more specific IDs such as `format.csv.structure`; see the [Check ID index](checks.md#check-id-index) |
| always-emit | A check result that appears in the report even when it passes, so "no finding" is visible rather than inferred from an absent ID |
| readiness verdict | The synthesized Ready / Revisions needed / Blocked / Not yet reviewed banner on the Review page, computed from findings, metadata completeness and dispositions |
| hush-scan / piigex | Required, bundled scanners for secrets and structured personally identifiable information (PII). Their absence is not reported as a "Missing …" warning because they ship with the app |
| Automated checks card | The dataset-page card listing dataset-level check results. It is distinct from the File checks tree, which holds per-file results |
