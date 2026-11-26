!!! warning "Historical snapshot"
    This page is a frozen proposal snapshot kept for provenance. It is intentionally **out of the site navigation** and is not a statement of current behaviour. See [Architecture](https://github.com/isaacpratt/dataverse-curation-app/blob/master/docs/internal/explanation/architecture.md) and the [design records](https://github.com/isaacpratt/dataverse-curation-app/blob/master/docs/internal/explanation/design-records/index.md) pointer for the live picture.

# Dataset review page — Top 10 improvement proposals

Prepared for the dataverse-curation-app · 6 Nov 2026 · companion report: other-ideas-dataset-review.md (22 more ideas)

These ten proposals were selected from 32 generated after a critical walkthrough of the dataset page (ui/dataset/, ui/workflow.py, ui/checks_tree.py, ui/dashboard.py), the check engine and contracts (engine/, curation/metadata_check.py, curation/review_rules.py, curation/response_draft.py, curation/storage.py), and current curation practice: the DCN CURATE(D) workflow and primers, the HEAL Data Packaging Tool and VLMD utilities, the Digital Research Alliance of Canada's Dataverse Curation and Metadata guides, Dataverse's Curation Status API and QDR's curation tools, and F-UJI / FAIR assessment practice.

The page is already strong: a six-step workflow rail, rule-driven metadata checks with editable rulesets and response templates, a depositor draft letter, version diffing, a curation timeline, PII and secrets scans, and checksum-verified downloads. Every idea below is net-new on top of that reality — several "obvious" ideas (README detection, PII scan, ORCID checks) already exist and were excluded. Each idea was scored independently against the rubric; nothing was ranked by taste.

## How the 32 ideas were evaluated

Each idea scored 1–5 on four axes, independently: Curator impact (×3 — does it make review more straightforward, intuitive, informative), Practice alignment (×2.5 — does it operationalize a step that DCN / HEAL / the Alliance guides / Dataverse tooling treat as standard), Feasibility (×2 — fits existing seams: rulesets v2, state.db, the report contract, the client's curation APIs), and Risk safety (×1 — higher means lower risk of surprising the curator or corrupting state). Maximum 50. The ten below scored ≥ 35; the other 22 are in the companion report. Effort tags (S/M/L/XL) are informational only — none of these was filtered by cost.

## The ten proposals

### 1 · Per-finding dispositions — let curator decisions survive a re-run

**Decision layer** · **Effort:** M40.5 / 50 · Impact 5 · Practice 5 · Feasibility 4 · Safety 5

**Desired outcome** — Every finding — auto-check result or incomplete metadata rule — can be marked Acknowledged / Fix requested / Won't fix / Blocked with a one-line note. Dispositions persist across sessions and re-runs, colour the Auto-Checks rows and manifest check-nodes, automatically exclude "Won't fix" findings from the depositor letter, and roll up as "3 of 9 findings resolved" in the checks summary.

**Summary of code changes** — Add an additive table finding_dispositions(dataset_id, finding_key, disposition, note, updated_at) to curation/storage.py (CREATE TABLE IF NOT EXISTS, so no migration). finding_key = stable hash of (check_id, file path, normalized message), so a re-run that reproduces a finding re-attaches its disposition while genuinely new findings start unresolved. Add a disposition combo + inline note to DatasetDetailView._auto_row() and the ui/checks_tree.py check nodes; filter curation/response_draft.py's collect_metadata_sections()/collect_filecheck_sections() by disposition; surface the roll-up count in _refresh_curation_preview().

**Why it's a good idea** — Today a curator's judgment lives in exactly one fragile place: the response-draft checkbox list, which resets whenever findings change, plus a single dataset-level free-text notes box. Curation is iterative — re-running checks (encouraged by the workflow rail) currently erases the curator's memory of "I already told the depositor about this one". DCN's Request step explicitly requires tracking provenance of any changes and why, and the Document step requires a curator log; this is the data structure both need. It is also the foundation the curation-record export (idea 4) and the verdict card (idea 2) consume.

**Sources:** DCN CURATE(D) Request + Document steps (z.umn.edu/curate); DCN Curator Log practice.

### 2 · A readiness verdict card — one answer to "where does this stand?"

**Decision layer** · **Effort:** M40 / 50 · Impact 5 · Practice 4 · Feasibility 5 · Safety 5

**Desired outcome** — A compact banner at the top of the Review page stating a synthesized verdict — Ready / Revisions needed / Blocked / Not yet reviewed — with reason chips ("2 required metadata fields missing", "1 check error in data.csv", "README absent", "sensitivity review pending"). Each chip links to the card it came from. The verdict is recomputed live from data already in memory and printed in headless runs.

**Summary of code changes** — New pure module engine/verdict.py: assess(report, completeness_full, dispositions, ruleset, sensitivity) -> Verdict(reasons, level) — no Qt, no I/O, trivially testable (matches the ui/workflow.py pattern this repo already trusts). DatasetDetailView calls it whenever _refresh_workflow() fires; a new banner card renders level + clickable reason chips. Headless main.py prints the same verdict and factors it into exit codes.

**Why it's a good idea** — The page answers "what did you find?" richly but "what does it mean?" not at all: the curator must mentally join five cards (metadata completeness, file manifest, auto-checks, version diff, log) to decide anything. Every serious tool in this space converges on a roll-up: HEAL's packaging tool ends in an audit/"shareable" step, F-UJI rolls 16 FAIR metrics into one score with sub-scores, HEAL's vlmd validate returns a single pass/fail. A verdict that is computed — never stored as truth — keeps the curator in command while removing the synthesis tax from every dataset in the queue. It also gives the dashboard's "Needs action" metric something honest to count.

**Sources:** HEAL Data Packaging Tool (audit/shareable step, norc-heal/heal-data-pkg-tool); F-UJI FAIRsFAIR metrics (f-uji.net); HEAL vlmd validate.

### 3 · A structured sensitivity & ethics review gate

**Decision layer** · **Effort:** M39.5 / 50 · Impact 5 · Practice 5 · Feasibility 4 · Safety 4

**Desired outcome** — Before a decision can be committed, a short structured questionnaire records the human judgments no regex can make: human subjects involved? consent/IRB documentation referenced? direct identifiers or small-cell risk beyond the automated PII scan? Indigenous data — CARE considerations? restricted files covered by terms of access? Answers are stored per dataset, pre-filled from the existing PII/access findings, shown next to the decision combo, exported with the curation record, and (when the ruleset says a collection requires it) block "Approve" until completed.

**Summary of code changes** — New sensitivity.py: a declarative question schema (id, prompt, help text, type) persisted in state.db as sensitivity_reviews(dataset_id, answers_json, updated_at). A card on the Response page between the draft editor and the Assessment Action card. engine/checks/access_check.py and the PII scan results seed suggested answers. Rulesets gain an optional "requires_sensitivity": true flag; _on_commit() checks completion before allowing Approve. Included in the curation-record export.

**Why it's a good idea** — Sensitivity review is the one curation step that is universally prescribed and completely absent from the app's data model. The DRA Canada Dataverse Curation Guide makes privacy review an explicit stage; the CARE Principles ask specific, checkable questions for Indigenous data; NIH's DMS policy expects documented human-subjects handling; Dataverse's own curation-label examples include "Privacy Review". The automated PII scan (already ported from the R tools) catches patterns — but the decision "this email column is the contact person, not a leak" is exactly the human judgment curators make and institutions audit. Recording it costs minutes and converts an invisible judgment into evidence.

**Sources:** DRA Canada Dataverse Curation Guide (doi:10.5281/zenodo.5579819); CARE Principles for Indigenous Data Governance; NIH DMS policy; Dataverse AllowedCurationLabels examples ("Privacy Review").

### 4 · One-click curation record export (the "Document" step, made real)

**Decision layer** · **Effort:** S39.5 / 50 · Impact 4 · Practice 5 · Feasibility 5 · Safety 5

**Desired outcome** — A single "Export curation record" action writes curation-record// beside the dataset's workspace folder containing: the checks report (JSON + Markdown), the depositor response letter, the full curation timeline (versions, review submissions, label history, local actions), all per-finding dispositions with notes, the sensitivity questionnaire answers, the recorded decision and pushed curation label, and a SHA-256 manifest of staged files. One folder an institution can file, audit, or attach to a ticket.

**Summary of code changes** — New curation_record.py orchestrator (pure I/O composition, no Qt) that reuses the existing exports — DatasetReport.save/save_markdown, response_draft render, AppState.list_actions(), hash_file() from curation/client/ — plus the new dispositions (idea 1) and sensitivity (idea 3) stores, and writes a small index.json binding them. One button in the header actions row beside "Export reports"; one --export-record flag in headless mode.

**Why it's a good idea** — Everything the record needs is already produced by the app — it is just scattered across state.db, the workspace folder, and Dataverse itself, and reassembling it by hand is tedious enough that it rarely happens. DCN's Document step ("Document all curation activities… Curator Log, correspondence") is the standard this implements; QDR's dvCurator institutionalized the same pattern (a local curation folder per dataset with original + prepared versions and a file manifest). This is the cheapest idea in the top ten and the one that makes every other idea auditable. It also naturally becomes the attachment a curator drops into their institution's ticket system or Dataverse correspondence.

**Sources:** DCN CURATE(D) Document step; QDR dvCurator (Code4Lib Journal, "Open Source Tools for Scaling Data Curation at QDR").

### 5 · A rationale & remediation layer for every check

**Guidance** · **Effort:** M–L37 / 50 · Impact 4 · Practice 4 · Feasibility 5 · Safety 5

**Desired outcome** — Every failed check offers an expandable "Why this matters / How to fix it" pair, written for curators rather than engineers — e.g. for a delimiter-drift finding: "Mixed delimiters break parsers and are the most common cause of ingest failure; re-export the file with a single comma delimiter and quoting on." The same text flows into tooltips, the Markdown report, and the depositor response templates as an optional paragraph.

**Summary of code changes** — CheckResult (engine/checks/base.py) gains two optional fields, rationale and remediation, with a tolerant from_dict (old payloads keep working — the status.py taxonomy already established this compatibility pattern). Guidance text lives beside each check as class attributes or a CHECK_GUIDANCE dict in each module (later consolidated by the registry idea in the companion report). ui/checks_tree.py renders an expandable guidance node under failures; engine/report_md.py emits it; curation/response_draft.py appends it when a ruleset template opts in with a {remediation} placeholder.

**Why it's a good idea** — The engine's messages are precise but terse — they tell a curator what was found, never why it matters or what to do, so the meaning currently lives in the requirements tooltips of the metadata card alone and in institutional folklore. The DCN primers are precisely this genre of writing — per-format "here is why this check exists and how to satisfy it" — and this project already ports the R inspectors' logic; porting their pedagogy is a natural, low-risk extension. It shortens the distance from finding to fix, makes the depositor letter concretely actionable, and improves the checks' teaching value for new curators without changing a single pass/fail decision.

**Sources:** DCN data curation primers (datacurationnetwork.org/data-primers); CUR_Res_CurationTools (the ported R inspectors' documentation).

### 6 · A CURATE(D) overlay on the workflow rail

**Information architecture** · **Effort:** M36.5 / 50 · Impact 4 · Practice 5 · Feasibility 4 · Safety 4

**Desired outcome** — The six-step rail (metadata → changes → download → checks → export → respond) gains a practice view that maps its steps onto the DCN CURATE(D) letters — Check, Understand, Request, Augment, Transform, Evaluate, Document — each step carrying a live open-item count (R: "4 required fields missing"; T: "3 files in proprietary formats"; D: "decision not yet recorded"). Toggling between the mechanical and practice views is one click; both remain navigation-only.

**Summary of code changes** — Extend ui/workflow.py (already a pure, fully-tested derivation module) with derive_curated(inp) -> Workflow mapping CURATE(D) steps onto the existing flags/counts plus report summaries and metadata completeness — no new I/O, honouring the rail's "never stats, never acts" contract. WorkflowRail in ui/widgets.py accepts either step set with a small view toggle persisted per user. Counts come from engine.status.summarize(), _completeness_full, and the dispositions store.

**Why it's a good idea** — The current rail is honest but app-mechanical: it describes what the software does, not what curation is. DCN's CURATE(D) steps are the de-facto shared vocabulary for North American data curation — used for onboarding, training, and cross-institutional work — and the Alliance's Curation Guide similarly frames review as named stages. Mapping the page's flow onto that vocabulary costs almost nothing (the derivation module is already pure and tested) and pays off twice: trained curators instantly recognize the process, and new curators learn it from the tool they work in. Live counts turn the rail from a progress indicator into a to-do list.

**Sources:** DCN CURATE(D) steps (z.umn.edu/curate); DRA Canada Dataverse Curation Guide; DCN workshop curriculum.

### 7 · Variable-level metadata coverage, with a dictionary-draft generator

**New check** · **Effort:** L36.5 / 50 · Impact 4 · Practice 5 · Feasibility 4 · Safety 4

**Desired outcome** — Every tabular file gets a coverage meter: what fraction of its variables carry a label/description in Dataverse's variable metadata (for .tab ingests) or in the deposited file itself (SPSS/Stata labels — the engine already reads those). A "Draft data dictionary" action generates a CSV (variable name, human label, type, allowed values, missing codes) the curator can send to the depositor, and a dataset-level check flags tabular files with zero documentation.

**Summary of code changes** — curation/client/client.py gains get_variable_metadata(file_id) hitting the dataset version's file-level variable metadata (the same surface Dataverse's Data Curation Tool edits). New dataset-level check metadata.var_coverage in the registry, consuming the runner context (inventory) like access_check does, plus local label coverage reusing the existing pyreadstat dictionary work in dta_check/sav_check. The manifest tree gains a coverage cell for tabular rows; a generator dialog exports the draft dictionary (name/label/type/values), HEAL-vlmd-shaped (Frictionless-flavoured: name + description minimum).

**Why it's a good idea** — Variable-level metadata is the single most requested documentation layer for quantitative reuse — ICPSR requires codebooks, the DRA Metadata Best Practices guide devotes sections to it, Dataverse ships a whole "Data Curation Tool" for editing it, and HEAL built its vlmd schema (name + description as the floor) and an entire packaging tool around per-file data dictionaries. The engine checks file formats exhaustively but never asks "can a stranger tell what v14 means?" — the curator currently has no signal for this gap at all. The draft generator turns the finding into a ready-made ask for the depositor letter, which is exactly how curators request it today.

**Sources:** HEAL vlmd / healdata-utils (extract · start · validate, Frictionless-based); HEAL Data Packaging Tool per-file data dictionaries; Dataverse Data Curation Tool (varMetaData); DRA Canada Metadata Best Practices v3; ICPSR deposit requirements.

### 8 · README depth check + a pre-filled README builder

**New check** · **Effort:** M36.5 / 50 · Impact 4 · Practice 5 · Feasibility 4 · Safety 4

**Desired outcome** — README presence is already detected via content rules — this upgrades it to depth: the README is parsed for the standard sections (dataset & file overview, file inventory/naming, methodological information, missing-data codes, sharing & access), scored, and shown as a checklist. A builder generates a pre-filled README draft from what the app already knows (citation metadata, file inventory with sizes/formats, license, terms) that the curator can hand to the depositor to complete.

**Summary of code changes** — Extend curation/review_rules.py with a section_rules rule type (heading/substring probes per section) evaluated by a new dataset-level readme_check consuming the staged folder via the runner context, so it works headless too. New ui/readme_builder.py dialog assembling the draft from self._metadata + self._inventory (both already loaded), Cornell/recherche.data.gouv headings, exported to the dataset folder. Response template gains a {readme_sections} placeholder so the letter lists exactly which sections are missing.

**Why it's a good idea** — "Is there a README?" and "is the README any good?" are different review questions, and the app currently answers only the first. The DCN Understand step centres on reading documentation; the Cornell README template and recherche.data.gouv template define the canonical section set; HEAL's packaging tool goes further and ships a README generator as a core feature — precedent that curators want scaffolding, not just detection. Generating the draft from metadata the app already holds makes the deposit-review loop faster and the ask specific ("add Missing data codes") instead of generic ("add a README").

**Sources:** DCN CURATE(D) Understand step; Cornell University Readme Template for Data (Kozlowski 2025); recherche.data.gouv.fr README template; HEAL Data Packaging Tool (readme.py + template); Social Science Data Editors template README.

### 9 · Depositor follow-up tracker — review is a conversation, not a snapshot

**Workflow** · **Effort:** M36 / 50 · Impact 4 · Practice 4 · Feasibility 4 · Safety 4

**Desired outcome** — When a decision commits as "Revisions requested", the dataset enters a waiting on depositor state visible in the dashboard queue ("awaiting reply · since 14 Oct · 23 days"). When the draft version later changes server-side (the timestamps endpoint already provides lastUpdateTime), the queue and the page surface "depositor updated — re-run checks & diff", and a click re-enters the workflow at the Changes step. The follow-up closes automatically when the decision moves.

**Summary of code changes** — Record follow-ups in state.db (new additive follow_ups(dataset_id, opened_at, state) or reuse datasets.status, which is already reserved-but-unused). The dashboard already receives lastUpdateTime via metadata enrichment — add a "changed since decision" comparison in _merge_enriched_rows() and a queue column/pill; the detail view shows a banner with a "re-run checks" shortcut when the draft's timestamp postdates the decision entry in curation_actions.

**Why it's a good idea** — The DRA Curation Guide treats review as correspondence over days or weeks — yet the app's model is a single session: nothing remembers "I asked for changes on the 14th", so curators track follow-ups outside the tool in spreadsheets or inboxes, exactly where institutional memory goes to die. All the ingredients exist already (decision log entries, version timestamps, dashboard enrichment batches); this idea merely joins them. It turns the queue from a list of datasets into a list of obligations, which is how curation queues actually behave.

**Sources:** DRA Canada Dataverse Curation Guide (correspondence-driven staging); Dataverse timestamps API (already consumed by the app).

### 10 · In-app file preview — "open the files" without leaving the review

**Understanding** · **Effort:** L35 / 50 · Impact 5 · Practice 4 · Feasibility 3 · Safety 4

**Desired outcome** — Clicking a file in the manifest opens a preview card (in the sidebar, or under the tree): tabular files show the first rows with column types; text/markdown shows the head; images render a thumbnail; PDFs show page count + first-page text snippet; archives list their entries (the containers check already enumerates them). Previews read head bytes only — never whole files — and degrade gracefully when an optional library is missing, exactly like the checks' "Missing …" behaviour.

**Summary of code changes** — New ui/preview.py: a lazy preview widget keyed by extension, reusing the engine's optional-library conventions (missing_library() from _util.py) and, where available, Pillow/pypdf/openpyxl — the packaging already anticipates this. ui/checks_tree.py click signal routes to the preview; a stub in the sidebar shows "select a file to preview". No worker needed for head-byte reads under a few MB (guard with a size cap and offer "Open folder" beyond it).

**Why it's a good idea** — The very first thing every curation workflow prescribes is to open the files — DCN's Check step and the Alliance guide both start there — yet the app's only affordance is "Open folder", which ejects the curator into Explorer, breaks their place in the page, and quietly discourages spot-checking. QDR built dv-Previewers for exactly this reason: repositories that show files get reviewed faster. The engine already opens most of these formats to run checks, so the riskiest parsing work exists; this adds the view, not the parsing. Spot-checking in place also makes the "Understand" step real for binary formats curators can't otherwise eyeball.

**Sources:** DCN CURATE(D) Check step; QDR dv-Previewers (Code4Lib Journal 15436); DRA Canada Dataverse Curation Guide.

On approval, each accepted proposal becomes one bead (one outcome per bead), created from .beads/templates/bead-creation.md after a bd list/bd search de-duplication pass, with sequencing dependencies where the ideas build on each other (1 → 4, 5 → registry). The other 22 ideas live in other-ideas-dataset-review.md — say the word and any of them can join the batch.
