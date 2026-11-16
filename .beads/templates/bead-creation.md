# Bead creation template

Copy this structure into every new `bd create --description`. A bead is the unit of work — it must make sense to a future agent with no other context, in order (`bv` order), without reading the rest of the repo.

## Before you create

1. **Dedup check:** `bd list --json`, then `bd search "<keywords>"`. If a near-duplicate exists, link to it (`discovered-from:<id>`) instead of creating a new one.
2. **All-open check:** confirm the item is still planned and not already closed/shipped. Closed items live in `docs/html/proposals.html` (Shipped record) — never re-create them.
3. **Type + priority:** `bug` (broken), `feature` (new capability), `task` (tests/docs/refactor), `epic` (large feature with children), `chore` (maintenance). Priority `0` critical → `4` backlog. Default `2`.
4. **Dependencies:** an epic's children use `bd dep add <child> <epic>` (parent) and `bd dep add <later> <earlier>` (ordering) so `bv` shows the work order. Discovered follow-ups use `--deps discovered-from:<parent-id>`.

## Description sections (in this order)

```markdown
## Outcome
<What is true when this is done, in one or two sentences. Observable behavior, not implementation.>

## Context
<Why this exists: the source doc, critique line, user request, or shipped-record reference. Include file paths and line/section anchors so a future agent can find the original without this bead. If the source has since been superseded, say so.>

## Hooks
<Where it touches: files, functions, tests, docs to update together (e.g. Report contract stays in sync with schema changes).>

## Tests
<How it will be verified: unit tests in `engine/tests/` or `ui/tests/`, plus e2e/probe (`tools/probes/`) when the behavior is visual or threading-related. Include what passing looks like (e.g. specific assertions, pixel, or log lines). Note any logging to add on failure paths.>
```

## Rules

- **Self-contained markdown.** No "see above", no links to other beads as a substitute for context. If a bead depends on another, say what it depends on and why.
- **Future-self check:** could a new agent pick this up in 6 months with only the bead plus the repo? If not, add the missing context.
- **One bead, one outcome.** If it needs sequencing, split it and order with `bd dep add`.
- **Don't close the loop in the title.** Titles state the work (`Fix X`), not the result (`X fixed`).
- **Docs are part of the bead.** If it changes behavior, the hooks include the docs page that documents it (`docs/html/*.html`, `README.md`, `AGENTS.md`).
- **Changelog:** if the change is user-visible, add a bullet to CHANGELOG.md's Unreleased section in the same commit.
- After creating, run `bd show <id>` and read it back. Fix anything you have to make up from memory.
