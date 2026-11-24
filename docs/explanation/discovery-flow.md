---
page_type: explanation
tgdp_template: Concept       # Concept | Explanation
audience: developer          # curator | developer | contributor | all
---
# Why discovery works this way

Discovery answers two questions before any file is downloaded: which datasets exist in this Dataverse, and what state are they in? The app answers them with the Native/Search API alone — no direct database or Solr access — using a total-driven Search pass followed by a small, pooled enrichment batch. This page explains the reasoning behind that shape, the caps, and the cache-first paint. It does not list endpoints; those belong in the reference material.

## Why there is no crawler

An earlier release used a CLI crawler (`dvCurator`) to build the draft queue. Its upstream project restructured the command contract in 2026-10, which left the app depending on an interface that no longer existed (see the 2026-10-29 row in [Architecture's decision log](architecture.md#decision-log)). Removing the crawler removed a whole class of breakage: discovery now uses a documented Dataverse endpoint that ships with the instance itself. The practical consequence for you is that a frozen executable and a development run discover datasets the same way, with no second tool to install or version-match.

The trade-off is that Search is an index, not a database cursor. It counts documents rather than datasets, and it can lag the underlying records. The app accepts that trade-off and reconciles it explicitly instead of pretending the index is authoritative.

## Why the server's total drives the loop

Search is requested at `per_page=1000` with a subtree alias, and the first response carries `total_count`. That makes the page count known up front, so the progress ring can say "page 2 of 3" rather than show an indeterminate spinner. `start` is an offset, not a page number; each page is deduplicated by persistent ID.

Termination is deliberately belt-and-suspenders. The loop stops when the collected count reaches the server's total, when a page comes back short or empty, or when the runaway guard trips at 100 pages. A short page is the ground truth for a corpus that shifts during a long crawl, so it wins over a stale total. Whatever ended the pull, collected and total are reconciled and any gap is logged loudly. On the Borealis demo this found 2,097 datasets over three pages; the earlier flat 1,000-dataset cap had hidden roughly 52% of the repository.

Draft state needs care because the index can surface a published-plus-new-draft dataset as `RELEASED` while its `publicationStatuses` still contains "Draft". Draft and review markers anywhere in the payload win, and duplicate persistent IDs keep the draft row — otherwise work in progress disappears from draft filtering.

## Why enrichment is pooled and in-process

Search gives identities and coarse state; it does not give the byte total, the true depositor or the authoritative version state those curators act on. A second pass fetches one version document per candidate dataset and adds the real size, the depositor, the state and the draft's last update time. That last timestamp feeds the depositor follow-up signal: a long quiet draft is worth attention.

The enrichment pass is intentionally small. It runs drafts first — they are the curation candidates most likely to need action — with five workers and a per-refresh cap of 200 rows, and it keeps only sums rather than whole file arrays. The cap was measured rather than guessed: against a simulated 5,000-row collection with 100 ms GET latency, 50 rows cost about a second, 200 about four seconds, 1,000 about twenty, and an uncapped pass about a hundred. Each extra hundred rows costs roughly two seconds, and the queue paints progressively every 25 completions, so the cap bounds the tail without delaying the first sizes. Every refresh logs the cap and the number of attempted fetches to the in-app Log page (`Ctrl+L`), which makes a slow refresh attributable to the fan-out.

A refusal on one dataset no longer aborts the batch. It is recorded on that row — access state, reason code and the server's own words — and the other rows continue, because the Search call already proved the token works. Reads that cannot exist are not sent at all: the dataset read answers with whichever version the account may see, so a separate version probe is only added for a row the Search payload marks as under curation. For the reasoning behind classifying some 4xx answers as expected, see [Troubleshooting](../troubleshooting.md).

## Why the first paint comes from a cache

The dashboard keeps the last crawl per instance and collection in `dashboard_cache.json`. On startup you see that list immediately; the live pass then runs behind it and a diff reports what changed — new, updated and removed rows — instead of repainting the whole table and losing your place. Row fingerprints make the change-only refresh possible, and the cache is disposable: a cold start costs a slower first real pull, not a broken screen.

The same cache remembers the label dropdown union for each pull. Labels are deliberately fetched fresh rather than compiled into the app: the bulk curation report supplies them when the account is allowed to read it, with a per-dataset fallback otherwise, and an instance with no labels shows the neutral "All labels" entry. Curation state, including the current label and its history, is read through the client and written back when you record an assessment. Nothing about the label vocabulary is hard-coded, so two Dataverse instances can disagree without either being wrong.

## Why sizes are capped and rows are windowed

Two distinct limits protect responsiveness, and they are easy to confuse. Size caps bound how much of a single file the engine reads; the painting window bounds how many dashboard rows the GUI draws at once.

The original size is used for tabular files in the download quote, because that is what a curator is approving. The engine's scan caps limit samples, rows, members and pixels inside a check, keeping a pathological file from stalling a review. Separately, very large collections are painted through a 2,000-row window. A benchmark over 25,000 synthetic rows showed that filtering the full set costs about 13 ms while painting costs roughly 0.45 ms per row — about 0.9 seconds at 2,000 painted rows, two seconds at 5,000 and over seven seconds uncapped. Sorting told the same story. The window is therefore the largest cap whose full repaint stays inside a second; it was confirmed, not raised. Filtering and sorting still cover the entire collection, and the status line says how many rows the cap is hiding, so you are never looking at a silently truncated queue.

Both limits are recorded next to the constants they govern and are re-measurable with `uv run python tools/perf/bench_paint_window.py` and `uv run python tools/perf/bench_enrichment_cap.py`. Changing one without re-running the relevant benchmark would turn a measured decision into a guess.

## Where to go next

The design decisions that replaced the crawler are recorded in [Design records](design-records/index.md). Endpoint details, authentication and the approval-gated download flow are reference material; the engine's view of the resulting files is described in [Engine port](engine-port.md).
