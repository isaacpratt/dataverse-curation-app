---
page_type: explanation
tgdp_template: Concept       # Concept | Explanation
audience: developer          # curator | developer | contributor | all
---
# Design records

Some material is worth keeping because it explains *why* the app is the way it is, but it is not a guide to doing anything and not a lookup reference. This page points to that frozen design material so you can find the reasoning without mistaking it for current behaviour.

## Proposal snapshots — historical

The 2026-11 dataset-review critique produced two proposal reports. Both are **historical design records**: they capture a moment in the project's thinking, are intentionally out of the site navigation (`not_in_nav`) and are not statements of what the app does today. Their approved ideas became beads; for the live picture, start with [Architecture](../architecture.md), the ADR index below and `bd ready`.

- [Top 10 dataset-review proposals](../../../proposals/top10-dataset-review.md) — the approved dossier, with each idea's outcome, code changes, rationale and scoring.
- [22 further ideas for dataset review](../../../proposals/other-ideas-dataset-review.md) — the companion report, including the full source bibliography behind the critique.

The decision recorded here is that these snapshots stay as historical design records rather than being rewritten into quadrant pages. They were written for a specific review; recasting them as current guidance would make them both stale and misleading. Provenance is their job.

## Architecture decision records

The [ADR index](https://github.com/isaacpratt/dataverse-curation-app/tree/master/docs/adr) holds short, dated records of the repository-level decisions — toolchain, layout, packaging and security — that would otherwise be re-litigated whenever someone asks why something is the way it is. The current set covers uv/poe/pre-commit, the flat `main.py` layout, Ruff formatting, not shipping the app on PyPI, credential-store token storage, the `curation/` core, strict typing, strict-app/relaxed-tests, and the Zensical docs build. Each ADR states its context, decision, consequences and links, and a reversed decision is superseded by a new ADR rather than editing history. The UI-level decision history is summarised in [Architecture](../architecture.md#decision-log).

## Beads is the live plan

Issues and planning live in beads, not on these pages. Use `bd ready` to find unblocked work, `bd show <id>` for the detail of one item and `bd list` to browse the whole queue. If a frozen proposal or a page of prose ever disagrees with beads, beads win: the snapshots record what was proposed, beads record what is being done.

Planning data lives in a local Dolt database and syncs over git-compatible refs separately from the code branch. The passive JSONL export is not the wire protocol, so coordination happens through `bd dolt push` and `bd dolt pull`, not by treating the export as the source of truth.
