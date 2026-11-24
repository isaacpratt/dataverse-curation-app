---
page_type: how-to
tgdp_template: How-to
audience: curator
---

# Run automatic checks on a dataset

Run these steps on a dataset you have opened from the dashboard queue. If you need to open one first, see [review your first dataset](../tutorials/first-review.md).

## Steps

1. Open the dataset from the dashboard by double-clicking its row, or by selecting it and pressing `Enter`.

2. In the **File checks** header, select **Download Dataset**. The app shows a quote with the file count and total size (the original size for tabular files) before moving any data.

3. Review the quote and approve the download. If the dataset declares a [guestbook](../reference/glossary.md) — a form some datasets require before download — its fields appear in the same window, prefilled from your account. Fill any required field and continue. Progress shows a running total such as `12.4 MB`; tabular originals replace `.tab` files.

4. To stop a download, select **Cancel**. Staged files are kept and the truncated bundle part is removed.

5. Select **Run Automatic Checks**. If nothing is staged yet, the app stages the dataset first (showing the approval dialog), then runs every applicable check. After a dataset-only pass the button reads **Run File Checks**; after a full pass it reads **Re-run Automatic Checks**. Once everything is staged, the download button reads **Verify Files**.

6. Inspect the results in the two sections.

   - **Dataset checks** holds dataset-level results: the file inventory, access restrictions, embargo dates, and metadata completeness.
   - **File checks** holds per-file results in a folder › file › check tree. Files with issues expand automatically; use the text and status filters to narrow the tree. A file may show **Clean**, **Warning**, **Error**, **Skipped**, or **No automated check**.

7. Click a file to see its [preview](../reference/glossary.md) in the sidebar: the first rows, lines, entries, or pages of that file. Select **Open folder** to reveal the staged file instead.

8. Set a [disposition](../reference/glossary.md) — your recorded decision on a finding — on any result row. Use the combo on an **Automated checks** row, or right-click a check row in the metadata or manifest tree. Choose **Acknowledged**, **Fix requested**, **Won't fix**, or **Blocked**, and add an optional note. Dispositions persist and reattach when a re-run reproduces the same finding; **Won't fix** findings are left out of the generated response until you re-include them.

9. To refresh metadata without downloading files, select **Reload Metadata** in the **Dataset checks** header. This re-fetches the metadata fields and the file inventory.
