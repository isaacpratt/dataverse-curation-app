# Dataverse Docent

Desktop curation assistant for Alliance Dataverse instances. It pulls datasets submitted for review, lets the curator approve a download, runs automated format-specific checks on the files, checks metadata completeness, and presents per-file and dataset-level findings in a desktop GUI with an exportable curation report.

## Roadmap

The remaining plan lives in **beads** (`bd ready` for next work, `bd list` for the full queue, `bd show <id>` for detail). The docs in `docs/html/` mirror it; beads win on disagreement.

## Context

The app is built on two existing projects:

| Project | Role in this app |
| --- | --- |
| [CUR_Res_CurationTools](../CUR_Res_CurationTools) | R inspection scripts and functions ported into the Python check engine |
| [rdm-review-dashboard](../rdm-review-dashboard) | Reference for Dataverse interaction, review workflow state, and reviewer/admin access patterns |

