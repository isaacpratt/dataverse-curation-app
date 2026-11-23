---
page_type: tutorial
tgdp_template: Tutorial
audience: curator
---

# Review your first dataset

This tutorial walks you through one complete review in Dataverse Docent, a desktop curation assistant for [Dataverse instances](../reference/glossary.md). You connect to the Borealis demo, open a dataset from your [curation queue](../reference/glossary.md), stage its files, run the automatic checks, record your findings, and export a curation record.

## What you'll learn

- Connect to a Dataverse instance through Settings.
- Open a dataset from the dashboard queue.
- Stage its files and run the automatic checks.
- Inspect findings and mark their disposition.
- Draft a response and export a curation record.

## Before you begin

- Dataverse Docent is installed on Windows. If it is not, follow the [installation guide](../how-to/install.md).
- You have a folder to use as your [**workspace**](../reference/glossary.md) — a local folder where Dataverse Docent keeps staged files and records.
- You do not need an [API token](../reference/glossary.md) for this tutorial: the Borealis demo can be browsed publicly. An API token is a credential that unlocks drafts and review states; without one you see only published datasets.

## Steps

1. Launch Dataverse Docent. If you installed the Setup.exe, open it from the Start menu. If you are running from source, open PowerShell in the repository and run:

   ```powershell
   uv run python main.py
   ```

   With no `config.json` present, the Settings page opens automatically.

2. Open Settings from the top nav, or press `Ctrl+,`. Under **Dataverse**, choose the **Borealis Demo** preset. This fills the **Base URL** with `https://demo.borealisdata.ca`.

3. Set the **Workspace** to a folder you can write to (for example `C:\Users\<you>\Documents\curation-workspace`), or use the default shown. Leave the API token blank and the [**collection alias**](../reference/glossary.md) empty. An empty collection alias means the whole repository; on the demo instance `dv` is the root alias, and `root` or `:root` are also treated as empty. For the meaning of each field, see the [configuration reference](../reference/configuration.md).

4. Select **Test connection**. Dataverse Docent calls `GET /api/info/version` and reports whether the instance answers.

5. Select **Save**. The dashboard loads the curation queue — the list of datasets available for review in the configured collection — and the status bar shows the current Dataverse and collection.

6. In the dashboard, double-click a dataset row (or select it and press `Enter`). The dataset detail page opens with its metadata and a file list.

7. In the **File checks** section, select **Download Dataset**. The app first shows a quote with the file count and size (the original size for tabular files). Review the quote and approve it. Any required [**guestbook**](../reference/glossary.md) fields — a short form some datasets require before download — appear in the same window; fill them and continue. Wait until the progress reaches its total. Your files are now [**staged**](../reference/glossary.md), meaning copied locally into the workspace.

8. Select **Run Automatic Checks**. Dataverse Docent stages the dataset first if you have not already done so, then runs every applicable check. The result pills show how many checks passed, warned, or failed.

9. Inspect the findings. **Dataset checks** hold results about the dataset as a whole (its file inventory, access conditions, and metadata completeness); **File checks** hold per-file results in a folder › file › check tree. Files with issues expand automatically. Click a file to see a [**preview**](../reference/glossary.md) — the first rows, lines, entries, or pages of its contents — in the sidebar.

10. Mark a finding's [**Disposition**](../reference/glossary.md) — your recorded decision on a finding — using the combo on a result row, or by right-clicking a row in a tree. Choose **Acknowledged**, **Fix requested**, **Won't fix**, or **Blocked**, and add a note if you want one. Dispositions persist and reattach when a re-run reproduces the same finding.

11. Open the **Response** page. It assembles standard text for the incomplete rules and failed checks. Clear the checkbox on any line you do not want to include, edit the text if needed, then use **Regenerate**, **Copy**, or **Export**.

12. Select **Export record** in the dataset header. Dataverse Docent writes a dated `curation-record` folder beside the dataset's workspace folder, containing the checks report (JSON and Markdown), the depositor response, the curation timeline, your dispositions, the sensitivity questionnaire, the recorded decision and curation label, and a `sha256sums.txt` manifest of the staged files.

## What you did

You connected to a Dataverse instance, reviewed one dataset from end to end, and produced both a depositor response and a local curation record. Use the [how-to guides](../how-to/run-checks.md) when you want to repeat a single step, and the [troubleshooting page](../troubleshooting.md) if a step does not work.
