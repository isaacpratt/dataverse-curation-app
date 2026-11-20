!!! warning "Historical snapshot"
    This page is a frozen proposal snapshot kept for provenance. It is intentionally **out of the site navigation** and is not a statement of current behaviour. See [Architecture](../../architecture.md) and the [Proposals](../../proposals.md) pointer for the live picture.

# Dataset review page — 22 further ideas

Companion to top10-dataset-review-proposals.html · same 32-idea generation and scoring pass · all net-new against the codebase as read on 6 Nov 2026 · all feasible; effort tags are informational only.

These ideas scored below the top ten on the shared rubric (Curator impact ×3, Practice alignment ×2.5, Feasibility ×2, Risk safety ×1) — usually because their payoff is narrower, their user is the maintainer rather than the curator, or a top-ten idea covers the same ground better. Several are strong candidates once the top ten land; each is written so it could be promoted to a bead without rework.

## Ideas 11–16 · Checks & evidence

### 11 · Statistical sanity probes for tabular files

New checkEffort: M35 / 50
IdeaExtend the CSV/XLSX checks (which already parse and find duplicate rows) with: all-NA columns, constant columns, implausible dates (year 2100+, negative durations), duplicate header rows, and value columns whose type flips mid-file. Emitted as warnings with the offending column names, capped lists, and details for the UI.
Changes · WhyNew probes in engine/checks/csv_check.py/xlsx_check.py beside the existing duplicate-row pass; no new dependencies. This operationalizes DCN's "Understand the data (QA/QC issues)" step and is the kind of defect curators catch by eye today — the machine should catch it first. Pairs naturally with the variable-metadata idea (a constant column is also a dictionary question).
Sources: DCN CURATE(D) Understand step (QA/QC checklist); CUR_Res_CurationTools tabular inspectors.

### 12 · Format-appropriateness advisor (preservation tiers)

New checkEffort: M34.5 / 50
IdeaAn informational dataset-level check mapping every extension to a preservation tier — recommended / acceptable / review-flagged (per DCN primer practice) — and naming the suggested open alternative (e.g. .docx data tables → CSV; 100-sheet .xlsx → split CSVs; .sav → also deposit a CSV export). Never fails; it advises.
Changes · WhyNew advice.formats dataset-level check fed by a small tier table in constants.py; renders in the Auto-Checks card as an advisory section. DCN's Transform step is exactly "transform file formats for reuse… open, non-proprietary formats", and the extension census the engine already computes is the data source — this adds the judgment layer on top. Keeps the curator's letter concrete ("please also deposit CSVs of the three .docx tables").
Sources: DCN CURATE(D) Transform step + format primers; DCN Data Curation Activities ("Transform files into open, non-proprietary file formats").

### 13 · Cross-file duplicate detection

New checkEffort: S34 / 50
IdeaDataset-level detection of identical files under different names (content hash, excluding the known .tab/original pairs the inventory already links), same-name collisions in different folders, and near-duplicate names (final.csv vs final_v2.csv vs final_FINAL.csv).
Changes · WhyExtend the inventory check (which already walks every file) with a hash pass reusing hash_file(); warnings only. Duplicate copies are among the most common findings in real deposits, they bloat storage and confuse reuse, and today only within-file duplicate rows are detected. Cheap, safe, and it feeds the naming-hygiene idea directly.
Sources: DCN Check step (file inventory); DCN Data Curation Activities (File Inventory/Manifest).

### 14 · File-naming hygiene check

New checkEffort: S34 / 50
IdeaImplement the dataset.filename_policy check the dispatcher's docstring already promises but the codebase never delivered: spaces and special characters, excessive length, version-suffix chaos (_v2_FINAL(1)), inconsistent date formats in names, and reserved-name risks.
Changes · WhyNew dataset-level check beside extensions_check using the same always-emit pattern; warnings with capped name lists. Naming problems break ingest, sorting, and machine readability, and both the DCN primers and repository guidance flag them routinely — the infrastructure expects this check to exist (it is literally named in engine/dispatcher.py line 5) which makes it the cheapest credibility fix in this list.
Sources: engine/dispatcher.py docstring (unfulfilled contract); DCN primers' file-naming sections; recherche.data.gouv README template ("File naming convention").

### 15 · Geospatial companion-file check

New checkEffort: S34 / 50
IdeaFor shapefile sets, verify the companion parts travel together (.shp needs .shx + .dbf, ideally .prj, plus sidecars); flag orphan parts and missing projections. Optionally extend to GeoPackage integrity (the gpkg_check already exists for single files).
Changes · WhyNew dataset-level check grouping inventory entries by directory; the inventory already carries directoryLabel paths. A shapefile missing its .prj is silently unusable for most GIS users — the classic geospatial curation trap that the DCN Shapefile primer exists to explain, and no check in the engine currently looks at file families at all.
Sources: DCN Shapefile primer; DRA Canada Metadata Best Practices (geospatial block guidance).

### 16 · Check-trend vs. the last run

FeedbackEffort: S29 / 50
IdeaStore summarize() counts (and the report timestamp) in state.db on every run; the Auto-Checks header then reads "3 errors · was 5 last run (2 Nov)" — direction-of-travel at a glance, including "new failure appeared".
Changes · WhyA new small table plus one line in the header summary the detail view already computes; pure additive state. Re-running checks is the loop the whole workflow encourages, but the app never says whether this run was better — a cheap signal that makes iteration legible, and the natural predecessor to the dispositions work.
Sources: internal consistency (the report cache already persists per dataset); QC practice of run-over-run deltas.

## Ideas 17–22 · Workflow, queue & guidance

### 17 · Recommended next-action CTA under the rail

Information architectureEffort: S34.5 / 50
IdeaOne primary button under the workflow rail computing the single best next action from current state ("2 files not staged → Download", "Checks not run → Run checks", "Decision not recorded → Respond") — the rail navigates by design and never acts, so the CTA completes it.
Changes · WhyThe derivation already exists in ui/workflow.py (current step + hint); this renders the hint's action as a button wired to the existing handlers. Keeps the rail's navigation-only purity while removing the "read the rail, then find the button" hop — the same pattern HEAL's step wizard uses (each step ends in its action).
Sources: HEAL Data Packaging Tool step flow; the app's own 2026-10-02 critique notes (no silent dead-ends).

### 18 · "Since your last visit" resume card

WorkflowEffort: M31.5 / 50
IdeaStamp last-visit per dataset in state.db; on reopen, a banner summarizes what changed server-side since then — new version, curation-label change, file-count/size delta, draft update — with the data already fetched by the metadata worker.
Changes · WhyA stamp + a diff over data the view already holds (_versions, _timestamps, _curation). Curators rotate through dozens of datasets across weeks; re-orienting costs real time, and the DRA guide's staged review assumes exactly these multi-week gaps. Stronger version of idea 9's signal, aimed at the returning curator rather than the waiting one.
Sources: DRA Canada Dataverse Curation Guide (staged, correspondence-driven review).

### 19 · Metadata "fix in Dataverse" deep links

MetadataEffort: S32.5 / 50
IdeaEach incomplete metadata check row gains a "fix in Dataverse" link straight to the draft's edit form (/dataset.xhtml?persistentId=…&version=DRAFT edit mode), so the reviewer can jump from "Affiliation missing" to the exact form without navigating the Dataverse UI.
Changes · WhyURL builders + one link per row in the metadata tree's Status cell (the header link already builds draft URLs this way). Review-to-fix distance is the loop curators run all day; the app currently ends the trail at the finding. Cuts the most repeated navigation in the review cycle to one click.
Sources: Dataverse dataset-page URL conventions; the app's existing draft-link logic in _update_header_link.

### 20 · Queue-level batch actions

WorkflowEffort: M31.5 / 50
IdeaMulti-select on the dashboard with batch operations: re-run checks on all staged, download all (each still individually approval-gated), bulk-apply a curation label, bulk-export curation records.
Changes · WhySelection + a batch bar on the existing queue table; reuses the per-dataset workers sequentially with progress. The curation-label API already supports per-dataset writes, and every operation remains consent-gated — this is volume ergonomics for curators whose queues number in the hundreds (the crawl already handles 1,300 rows).
Sources: Dataverse Curation Status API (bulk-friendly per-dataset writes); the app's own enrichment batching precedent.

### 21 · Declarative check registry (single source for text, docs & UI)

ArchitectureEffort: M31.5 / 50
IdeaEach check declares id, applies-to, level semantics, rationale, remediation, and primer link in one place; UI rows, the Markdown report, headless output, and the checks-reference documentation all generate from it.
Changes · WhyFormalizes what idea 5 starts: class attrs → a CheckMeta dataclass consumed by list_planned_checks, report_md, and a doc generator; docs/html/checks-reference.html gains a "generated" stamp. Kills the drift risk between engine messages, UI copy, and documentation as the check count grows — a maintainer-facing idea whose payoff is consistency.
Sources: the repo's own docs-as-contract practice (docs/html/checks-reference.html).

### 22 · Response letter: per-finding curator annotations

ResponseEffort: M31 / 50
IdeaBeyond including/excluding a finding in the draft letter, let the curator attach a sentence per included finding ("please use ISO dates for the coverage field"), merged into the generated paragraph via the existing placeholder system.
Changes · WhyPer-section note field feeding render_response() (templates already support arbitrary placeholders); persists with the working draft. Ruleset templates are one-voice-for-all-datasets; annotations make each letter match the dataset without hand-editing the whole draft — the difference between editing a form and editing a letter.
Sources: the app's ruleset/response-template architecture (curation/review_rules.py, curation/response_draft.py).

### 23 · Approve-with-conditions decision

Decision layerEffort: M31 / 50
IdeaA decision option that carries a checklist of required fixes (auto-built from open findings); conditions must be individually marked done (or waived with a note) before the label can be pushed as "Approved" — turning approval into a verifiable state rather than a word.
Changes · WhyBuilds on dispositions (idea 1) and the commit gate (_on_commit already gates + confirms remote writes). Mirrors how real curatorial approvals work in practice — "approve once X lands" — and gives the follow-up tracker (idea 9) a precise completion condition.
Sources: Dataverse curation labels ("Author contacted", "Awaiting paper publication" style states); DCN Request step.

### 24 · Decision correction (revert with history)

Decision layerEffort: S29.5 / 50
IdeaA "correct decision" affordance that appends a correction entry to the append-only log (never deletes), restores the combo, and re-prompts the remote-write confirmation if a curation label must change on the server.
Changes · WhySmall addition to _on_commit + log rendering. The log is append-only by design; misclicks currently require out-of-band fixing, and the provenance-first philosophy of the Document step argues for visible corrections rather than silent edits.
Sources: DCN Document step (provenance of decisions); the app's own remote-write confirmation pattern.

### 25 · Headless batch mode for CI / pre-ingest

ArchitectureEffort: M31 / 50
Idea--headless exists for one staged directory; add --batch  iterating staged dataset folders with the existing exit-code contract and one report per dataset, enabling pre-ingest gates in deposit pipelines or scheduled sweeps of a shared staging area.
Changes · WhyLoop + aggregate exit semantics over the existing main.py headless path; the engine is already pure and I/O-side-effect-free. Moves the same checks upstream in the deposit lifecycle — the Alliance's guide explicitly frames curation capacity as the bottleneck, and automating the first pass outside the GUI is how institutions scale it.
Sources: the app's headless contract (exit codes 0/1/2); DRA Canada curation-capacity framing.

### 26 · Report contract schema_version

ArchitectureEffort: S29.5 / 50
IdeaAdd schema_version to DatasetReport alongside engine_version, with a tolerant from_dict that migrates older payloads; the GUI records the version it rendered.
Changes · WhyOne field + a version switch in the strict parser (which today rejects "corrupt/foreign payloads" — future self-inflicted payloads included). The report is the shared contract between engine, GUI, and headless consumers; versioning it now is cheap insurance before ideas 1, 2 and 5 extend it.
Sources: the repo's own versioning precedent (TABLE_LAYOUT_VERSION, rulesets v2).

### 27 · Per-dataset metadata profile persistence

WorkflowEffort: S29 / 50
IdeaThe metadata profile combo resets to the default on every reopen; persist the curator's chosen profile per dataset in state.db so a dataset reviewed under "Minimal" stays under "Minimal".
Changes · WhyRead the saved profile in DatasetDetailView.__init__ instead of always DEFAULT_PROFILE; write on change. Small, but it silently changes review results today — a dataset's completeness count can shift between visits, which reads as the data changing when it is really the lens.
Sources: internal consistency; the app's persistence contract (table layouts already persist user choices).

### 28 · Sidebar section status chips

Information architectureEffort: S29 / 50
IdeaThe Sections nav lists per-card counts beside each link — Metadata 12/15 · Files 3 issues · Checks 2 errors — refreshed with the same in-memory data the cards use.
Changes · WhyBadges on _nav_buttons fed from existing summaries. The sidebar is the page's map; a map without traffic misses its second job — deciding whether a section needs a visit at all. Cheap companion to the verdict card (idea 2), which it feeds from.
Sources: the app's own section-nav design; dashboard metric-card pattern.

### 29 · License & terms verification panel

New checkEffort: M30 / 50
IdeaA panel (plus optional check) showing the dataset's license block, recognizing known licenses (CC variants, MIT, etc.), flagging "no license / custom terms", and pairing with the restricted/embargo findings access_check already surfaces so reuse conditions are readable in one place.
Changes · WhyThe license block is in the metadata the view already holds; access_check already extracts termsOfAccess and embargo dates. DCN's Evaluate step names "transparent usage licenses" first; reuse rights are the number-one downstream question about any dataset, and today they are scattered across the raw metadata tree and the timeline.
Sources: DCN CURATE(D) Evaluate step; F-UJI R1.x metrics (licence named in FAIR metrics); DRA Canada Metadata Best Practices.

### 30 · Keyboard triage & full a11y audit

AccessibilityEffort: M31 / 50
IdeaDataset-page shortcuts (run checks, download, filter focus, expand/collapse, jump to next finding, toggle response) beyond the three window-level shortcuts that exist today; then a WCAG 2.1 AA pass over the new surfaces, extending the palette→role→contrast contract already enforced in theme.py.
Changes · WhyQShortcuts + an audit pass with the existing contrast test suite as the harness. High-volume reviewers live on the keyboard; the app's accessibility culture (accessible names everywhere in the code) deserves a completion pass rather than per-feature retrofitting.
Sources: WCAG 2.1 AA; the repo's contrast-contract tests (test_contrast.py, test_theme_conformance.py).

### 31 · Bilingual EN/FR groundwork

AccessibilityEffort: L29 / 50
IdeaThe string catalogue (ui/assets/strings.json via t()/tn()) is already fully externalized and guard-tested — this adds the French catalogue and a language setting, with the string guard extended to assert key parity.
Changes · WhyA second catalogue + a setting + parity tests. Borealis is officially bilingual and the Alliance context makes French support a plausible institutional requirement; the architecture is already language-ready, so this is breadth rather than surgery. Not urgent for a single-institution tool — hence its position here.
Sources: Borealis (bilingual Canadian Dataverse repository); the app's i18n guard tests.

### 32 · Dark mode

DesignEffort: M28.5 / 50
IdeaThe planned dark-mode step, executed through the existing palette→semantic-role→contrast-contract pipeline: a second palette producing the same roles, with the contrast tests asserting both.
Changes · Whytheme.py's architecture was built for exactly this (roles and contrast contracts are palette-independent); the work is the second palette and the test matrix. Listed last because it is polish — but it is also the proof that the theme layer kept its promise.
Sources: the app's own development docs (planned dark-mode step) and theme architecture.

## Sources consulted

- Data Curation Network — The DCN CURATE(D) Steps (z.umn.edu/curate) and the CURATE(D) checklists; Data Curation Primers (github.com/DataCurationNetwork/data-primers); DCN Data Curation Activities glossary; DCN workshop curriculum.
- HEAL Data Ecosystem — healdata-utils (vlmd: extract / start / validate; Frictionless-based variable-level metadata schema; github.com/HEAL/healdata-utils); HEAL Data Packaging Tool (desktop tool; study-level experiment/resource trackers, per-file results trackers and data dictionaries, package audit & shareable state; github.com/norc-heal/heal-data-pkg-tool); HEAL Platform VLMD documentation.
- Digital Research Alliance of Canada — Dataverse Curation Guide (doi:10.5281/zenodo.5579819) and Dataverse Metadata Best Practices Guide v3 (doi:10.5281/zenodo.5576411); the ported CUR_Res_CurationTools R inspectors; Borealis service description (bilingual Canadian Dataverse).
- Dataverse / QDR — Dataset Curation Status API (guides.dataverse.org, curation-labels; assigner + history per IQSS PR #11268); the built-in Data Curation Tool for variable-level metadata; QDR's dvCurator and dv-Previewers (Code4Lib Journal, "Open Source Tools for Scaling Data Curation at QDR").
- README templates — Cornell University Library, Readme Template for Data (Kozlowski 2025); recherche.data.gouv.fr README template; Social Science Data Editors' template README.
- FAIR & ethics — F-UJI automated FAIR assessment (FAIRsFAIR metrics, f-uji.net); FAIR-IMPACT assessment-tools listing; CARE Principles for Indigenous Data Governance; NIH HEAL data-sharing policy materials.
