# Diátaxis quadrant audit

This report records the intended quadrant and TGDP template of every published page after the Diátaxis rewrite (bead `dv-uq6`). It is a tracked report under `docs/reports/` and is excluded from the site build; it has no front matter.

## Quadrant audit table

| Page | page_type | TGDP template | Disposition/notes |
| --- | --- | --- | --- |
| `index.md` | home | Home | Site entry point and quadrant map; not a quadrant page. |
| `tutorials/first-review.md` | tutorial | Tutorial | Learning-oriented walkthrough of a first review. |
| `how-to/install.md` | how-to | Installation guide | Goal-oriented install recipe. |
| `how-to/configure-instance.md` | how-to | How-to | Goal-oriented instance and token setup. |
| `how-to/run-checks.md` | how-to | How-to | Goal-oriented check run. |
| `how-to/respond-and-export.md` | how-to | How-to | Goal-oriented response draft and report export. |
| `how-to/run-headless.md` | how-to | How-to | Goal-oriented headless scan. |
| `how-to/add-a-check.md` | how-to | How-to | Developer task steps for extending the engine. |
| `how-to/run-the-gates.md` | how-to | How-to | Developer task steps for the local gate. |
| `how-to/package-and-release.md` | how-to | How-to | Developer task steps for packaging and publishing. |
| `reference/checks.md` | reference | Reference | Factual check semantics and issue taxonomy. |
| `reference/report-contract.md` | reference | Reference | JSON report contract. |
| `reference/configuration.md` | reference | Reference | Configuration keys and environment overrides. |
| `reference/dataverse-api.md` | reference | Reference | Native/Search API endpoints and auth. |
| `reference/cli.md` | reference | Reference | Command-line arguments and exit codes. |
| `reference/entry-checks.md` | reference | Reference | Entry-correctness check catalogue. |
| `reference/project-layout.md` | reference | Reference | Repository layout and suite locations. |
| `reference/ui-wireframe.md` | reference | Reference | Numbered widget map with a Qt class, objectName, layout and bounds legend. |
| `reference/glossary.md` | reference | Glossary | Alphabetical term definitions. |
| `explanation/architecture.md` | explanation | Concept | Components, threading, storage, layering. |
| `explanation/discovery-flow.md` | explanation | Concept | Why discovery and enrichment work as they do. |
| `explanation/entry-correctness.md` | explanation | Concept | Rationale behind the entry-correctness rules. |
| `explanation/engine-port.md` | explanation | Concept | R-to-Python port matrix and decisions. |
| `explanation/ui-conventions.md` | explanation | Concept | Theme, table and widget contracts. |
| `explanation/design-records/index.md` | explanation | Concept | Index of architecture decision records and their rationale. |
| `troubleshooting.md` | troubleshooting | Troubleshooting | Symptom-led diagnosis and fixes. |
| `release-notes.md` | governance | Release notes | Channels and condensed change summary. |
| `style-guide.md` | governance | Style guide | In-repository rules for documentation authors. |

## Historical and retired material

`docs/proposals/*.md` are frozen historical design records. They are deliberately out of the Zensical navigation (`not_in_nav`) and carry a "Historical snapshot" admonition. They are not quadrant pages and are not maintained.

`docs/html/` was the hand-authored pre-Zensical site. It was retired by this rewrite and is no longer part of the documentation source tree. All edits go to the Markdown tree in `docs/`.
