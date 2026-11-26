---
page_type: troubleshooting
tgdp_template: Troubleshooting
audience: all
---

# Troubleshooting

Find the message or symptom you see, then apply its fix. For setup steps, see [configure a Dataverse instance](how-to/configure-instance.md); for the meaning of a term, see the [glossary](reference/glossary.md).

| Symptom | Cause | Fix |
| --- | --- | --- |
| `401` | The API token expired or lacks permission for the dataset; a `401` on one dataset's draft can also be the server's expected answer for a draft your account cannot read. | Regenerate the token in Dataverse and update it in **Settings** (`Ctrl+,`). For a draft-specific `401`, check that row's **Access** column — it is expected, not a token problem. |
| `ConnectionResetError 10054` | A transient network reset. | The app retries three times automatically. Check your VPN or proxy, then retry. |
| `400 invalid collection alias` | The collection alias does not identify a collection in that instance. | Try an empty alias for the whole repository. On the Borealis demo the root alias is `dv`, not `borealis`. |
| Empty dashboard | No datasets exist for that subtree, or you have no API token and only published datasets are returned. | Widen or clear the collection, or add a token in **Settings**. |
| `Missing: pip install …` | An optional library is absent from a development environment. | A shipped build carries every library, so reinstall it; in a development environment, install the named library with `uv add <package>` and re-run `uv sync`. |
| Check "not executed" | An optional external tool is missing. | Install `tesseract` (OCR) or `exiftool` (deep metadata) and set its path in **Settings**. |
| `ContextualVersion 406` | An old build sent a versioned URL without `&` before `persistentId`. | Fixed in current builds — re-pull the metadata if you saw this on an old build. |
| Download interrupted | A network interruption or a cancelled transfer. | Re-download. The previous stage is cleaned up and prior reports are preserved. |
| Download says "Guestbook response" required | The dataset collects a [guestbook](reference/glossary.md) before download. | Fill any required field in the download window (prefilled from your account) and submit it. If the form did not appear, reload the dataset metadata and try again. |
| Checksum mismatch on `.tab` | The server regenerates the tabular ingest product, so its checksum differs. | Compare the UNF in the message, or fetch the original format. A mismatch on any other format is real corruption — re-download it. |
| `NameError: QWidget` in Settings | An older release's Settings bug. | Update to the latest release from [GitHub Releases](https://github.com/isaacpratt/dataverse-curation-app/releases). |

## Expected log lines

Some lines on the Log page are the server's documented answer for a request, not application failures. They are tagged **EXPECTED** and shown in a muted tone, with the reason placed after the raw response — for example `GET …/versions/:draft → 403 EXPECTED — draft_not_readable: this account is outside the dataset's curation scope`. Anything the app cannot classify — a `500`, a bad request, or a wrong path — stays **ERROR** in red.

| Refusal | When it is expected |
| --- | --- |
| `401` / `403` on `…/versions/:draft` | Your account cannot read the draft — Dataverse grants draft access only inside a dataset's curation scope. |
| `404` on `…/versions/:draft` | The dataset has no draft version. |
| `404` on `…/versions/:latest` or `…/versions/:latest-published` | The dataset has no published version; deaccessioned versions are excluded by default. |
| `403` on `…/curationStatus` | Curation state exists only for datasets under curation and only for accounts in their curation scope. |
| `404` on `…/versions/:latest-published/compare/:draft` | There is no published/draft pair to compare. |

The dashboard's **Access** column carries the same facts per dataset: **Draft not readable**, **Not readable**, **No published version**, or **Curation state hidden**, and it is empty when everything could be read. Hover the cell for the reason and the server's own words.
