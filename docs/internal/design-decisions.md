---
page_type: explanation
tgdp_template: Concept
audience: developer
---
# Design decisions and decision log

Internal context for maintainers. None of this is needed to use the app; the public site deliberately keeps it out. The fuller rationale lives in [Architecture](explanation/architecture.md), [Discovery flow](explanation/discovery-flow.md), [Engine port](explanation/engine-port.md), [Entry correctness](explanation/entry-correctness.md) and [UI conventions](explanation/ui-conventions.md). The frozen snapshots are in [Design records](explanation/design-records/index.md).

## Decision log

A condensed record of the decisions that shaped the current shape. The full history lives in the repository's decision records and beads.

| Date | Decision |
| --- | --- |
| 2026-08-17 | PySide6 single-process desktop; API-token auth; Python port over portable R (~400 MB). |
| 2026-08-21/25 | CLI draft crawl and IN_REVIEW locks; paginated Search fallback; streaming download; connection-reset retry; metadata completeness as a first-class feature; lazy imports. |
| 2026-09-08/15 | Detail main + sticky sidebar; settings/about as stack panes; log strip became the Log page; problems-vs-warnings verification; originals-only tabular deposits; skip-if-staged; QThread adoption; dashboard cache-first paint. |
| 2026-09-11/23 | `ui/widgets.py` kit as single source of truth (a QML UI was rejected); audit batches for dispatch, missing-lib guards, atomic staging, retries, caps and taxonomy. |
| 2026-09-25 → 10-02 | Theme tokens single-sourced; keyboard parity and plain-language errors; colour-not-outline focus; Copy diagnostics that never include the token. |
| 2026-10-06 | Dataverse Docent rebrand; probe suites promoted to permanent tests and CI. |
| 2026-10-29 | The crawler was removed after its upstream restructure broke the CLI contract. Discovery became total-driven Search at `per_page=1000` plus in-process pooled inventory enrichment; a painted-row window was added for very large collections. |
| 2026-11-04 | One layout controller per table header, persisting user gestures only; the queue's split header demoted to an opt-in fallback; one reset-columns affordance; one type scale; versioned layout entries. |
| 2026-11-06 | Beads became the planner: issues live in a local Dolt database, `bd ready` is the queue, and docs/proposals mirror rather than lead. |
| 2026-11-07 | Card header contract: titles and tools on separate rows; one decimal size helper; measured first-load geometry. |
| 2026-11-12 | Metadata check restyled to the Auto-Checks idiom; human-readable check names from one registry; expected API refusals classified rather than reported as bugs. |
| 2026-11-13 | Entry-correctness rules (`looks_correct`) added with fail-closed semantics; review configuration gained a Check picker and an entry-checks panel. |
| 2026-11-16 | Velopack replaced the earlier installer plan; user-editable files moved to `%APPDATA%`; the curation core was consolidated under `curation/`. |
| 2026-11-16 | One name and one build: the app, the artefact, the installer and the distribution all say Dataverse Docent; the two-variant build was removed. |
| 2026-11-17 | The dataset detail module was split into a facade over ten section modules sharing one typed contract; the queue painting window and enrichment cap were measured and confirmed. |
| 2026-11-19 | Every check now declares its scope; the Python floor was made 3.11 everywhere; dependency floors were aligned with what ships. |
| 2026-11-20 | All application code moved to full strict type checking with only tests relaxed; documentation moved from hand-authored HTML to a Markdown tree built by Zensical and configured for GitHub Pages. |
| 2026-11-23 | The docs were rewritten into Diátaxis quadrants with TGDP templates, and the old HTML tree was retired. |

## Rationale collected from public pages

These notes were removed from the public reference pages because they explain choices and record progress rather than describing how to use the app.

### Discovery and search

- An earlier release used a CLI crawler (`dvCurator`). Its upstream project restructured the command contract in 2026-10, leaving the app depending on an interface that no longer existed. Discovery now uses a documented Dataverse endpoint that ships with the instance, so frozen and development runs behave the same.
- Search is an index, not a database cursor: it counts documents rather than datasets and can lag the records. The app reconciles collected against total and logs any gap instead of treating the index as authoritative.
- Verification snapshot (point in time, 2026-11-03): observed against `https://demo.borealisdata.ca`. Version → Borealis; search `subtree=mcmaster` → 14 datasets in one page; whole repository → 2,097 datasets over 3 pages at `per_page=1000`; dataset lookup → citation title OK; versions → 23 files; bundle → 358 477 bytes streamed and unzipped. Empty alias and `:root` return the whole repo; root alias is `dv`. The demo is a real Borealis Dataverse deployment (v6.8.4-SP); a token-backed authenticated pass was deferred.

### Check engine

- The checks are ports of the R inspectors in `CUR_Res_CurationTools`; no R runtime ships with the app. This is a design record, not an instruction for curators.
- Each check declares a scope (`dataset` or `file`) at registration; the registry refuses a class without one and the dispatcher routes on that declaration. Extensions say which files a check reads, not what its findings are about. This is why a cross-file check can be dataset-scoped.
- Secrets/PII scanners use `regions=["intl"]` plus the Canadian postal/SIN pack; foreign national IDs are disabled by policy. `scipy` stays out of the dependency set, so MATLAB `.mat` surfaces through the unchecked-types hint rather than a dedicated check.
- Download verification is a gate, not a check: it is not part of the check registry.

### Entry-correctness rules

- `looks_correct` is dispatched like any other field-rule handler, so enabling a plausibility check is editing data rather than installing code. The cost is that plausibility must be expressed as a completeness result, because that is all the pipeline understands.
- Rollout posture: the built-in rulesets contain zero `looks_correct` rules. A plausibility rule that fires on valid deposits erodes trust faster than a miss, so enrollment is visible in the ruleset rather than hidden in an application setting.
- External services are deliberately absent: no DOI, Crossref or ORCID resolution, so a rule and a value always produce the same verdict.
- Scope limits are deliberate: plausibility is not truth; `min_length` counts codepoints; ISO-only dates reflect a repository convention; a regex is the curator's responsibility; live identifier resolution and negation would be new handlers.

### Troubleshooting history

- `NameError: QWidget` in Settings was a bug fixed in the 2026-08-26 build. The public troubleshooting page now tells the reader to update rather than carrying the date.

### Documentation and tooling

- Documentation is code: Markdown in `docs/`, reviewed with the app, built with a strict Zensical build, Markdown lint, offline link checks, generated-reference checks and doc-to-code tests. External links are checked on a schedule so a third-party outage cannot block a docs change.
- Local tooling caches (`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.pyi-cache/`, `__pycache__/`) live in the working directory and are gitignored; they are not application artefacts.
