"""Benchmark: the dashboard's per-refresh enrichment cap (bead dv-gj9).

The crawl enriches thin search rows with live inventory sums, the
depositor and the authoritative state. Every enriched row costs one
version fetch, so the cap is a completeness/fetch-count trade-off:
a small cap refreshes quickly and leaves most rows without a size, a
large cap fills the queue but asks the server for thousands of version
documents per refresh.

This harness measures that trade-off without a network: the client is
real, the version fetch is a stub with a simulated latency (the
Dataverse GET round trip), and the fetch count is counted exactly.

Run::

    uv run python tools/perf/bench_enrichment_cap.py
    uv run python tools/perf/bench_enrichment_cap.py --rows 5000 --latency-ms 100
    uv run python tools/perf/bench_enrichment_cap.py --markdown   # for the docs
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ROWS = 5_000
DEFAULT_CAPS = (50, 100, 200, 400, 1_000, 2_000, -1)
DEFAULT_LATENCY_MS = 100
WORKERS = 5
FLUSH_EVERY = 25  # the worker's progressive-paint batch size


def _synthetic_rows(count: int) -> list[dict]:
    """Build a synthetic collection: thin search rows, no sizes yet."""
    rows = []
    for i in range(count):
        rows.append(
            {
                "title": f"Dataset {i:06d}",
                "persistent_id": f"doi:10.5072/FK2/SYN{i:06d}",
                "state": "DRAFT" if i % 4 == 0 else "RELEASED",
                "total_size_bytes": None,
            }
        )
    return rows


def _stub_client(latency_s: float):
    """Build a real client whose version fetch is a counted, timed stub."""
    from curation.client.client import DataverseClient

    client = DataverseClient(base_url="https://example.invalid", api_token="stub")
    state = {"fetches": 0, "first_flush_s": 0.0, "started": 0.0}

    def _fake_fetch(pid: str, fall_back_on_auth: bool = True):
        if state["started"] == 0.0:
            state["started"] = time.perf_counter()
        time.sleep(latency_s)
        state["fetches"] += 1
        payload = {
            "files": [{"dataFile": {"id": 1, "filesize": 1_048_576}}],
            "versionState": "RELEASED",
            "depositor": "Synthetic Depositor",
        }
        return payload, "draft", []

    client._fetch_version_data = _fake_fetch  # type: ignore[method-assign]
    return client, state


def _measure(rows_count: int, cap: int, latency_s: float) -> dict[str, float]:
    """Run one enrichment pass under one cap and time it."""
    client, state = _stub_client(latency_s)
    rows = _synthetic_rows(rows_count)

    def _progress(done: int, total: int) -> None:
        if done >= FLUSH_EVERY and state["first_flush_s"] == 0.0:
            state["first_flush_s"] = time.perf_counter() - state["started"]

    start = time.perf_counter()
    stats = client.enrich_datasets_with_inventory(
        rows,
        max_rows=cap,
        max_workers=WORKERS,
        progress=_progress,
    )
    elapsed = time.perf_counter() - start
    return {
        "seconds": elapsed,
        "fetches": float(state["fetches"]),
        "enriched": float(stats.get("enriched", 0)),
        "pending": float(stats.get("pending", 0)),
        "first_flush": float(state["first_flush_s"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--caps", type=int, nargs="+", default=list(DEFAULT_CAPS))
    parser.add_argument("--latency-ms", type=float, default=DEFAULT_LATENCY_MS)
    parser.add_argument("--markdown", action="store_true", help="print a markdown table")
    args = parser.parse_args(argv)

    latency_s = args.latency_ms / 1000.0
    results = []
    for cap in args.caps:
        result = _measure(args.rows, cap, latency_s)
        results.append((cap, result))
        label = "uncapped" if cap < 0 else str(cap)
        if not args.markdown:
            print(
                f"cap {label:>8}: {result['seconds']:.2f}s  fetches {int(result['fetches']):>5}  "
                f"enriched {int(result['enriched']):>5}  pending {int(result['pending']):>5}  "
                f"first paint {result['first_flush']:.2f}s"
            )

    if args.markdown:
        print("| cap | fetches per refresh | refresh time | first painted rows |")
        print("| --- | --- | --- | --- |")
        for cap, result in results:
            label = "uncapped" if cap < 0 else f"{cap:,}"
            print(
                f"| {label} | {int(result['fetches']):,} | {result['seconds']:.1f} s | "
                f"{result['first_flush']:.1f} s |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
