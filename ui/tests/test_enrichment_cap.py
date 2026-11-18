"""Contract: the enrichment cap is a measured value and says so in the Log.

The dashboard's crawl patches thin search rows with live file sizes,
one version fetch per row. How many rows it patches per refresh is a
completeness/cost trade-off, so the number is benchmarked
(``tools/perf/bench_enrichment_cap.py``) and every refresh logs the cap
together with the fetch count it actually spent.
"""

from __future__ import annotations

import pathlib
import re

from ui.workers import CrawlWorker

_TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "perf" / "bench_enrichment_cap.py"


def test_the_cap_is_the_measured_value():
    """200 rows: ~4 s of background enrichment for 200 version fetches."""
    assert CrawlWorker._ENRICH_MAX_ROWS == 200
    assert CrawlWorker._ENRICH_WORKERS == 5
    # Drafts first, so the capped budget lands on curation candidates.
    assert CrawlWorker._ENRICH_FLUSH_EVERY == 25


def test_the_cap_is_documented_where_it_lives():
    """A measured constant carries its numbers, so it is not re-guessed."""
    from ui import workers

    text = pathlib.Path(workers.__file__).read_text(encoding="utf-8")
    assert "dv-gj9" in text
    assert "bench_enrichment_cap" in text


def test_the_refresh_logs_the_cap_and_the_fetch_count():
    line = CrawlWorker._enrichment_log_line(200)
    assert "200" in line
    assert "5" in line
    assert "200 fetches attempted" in line
    assert re.search(r"cap\s*:?\s*200", line, re.IGNORECASE), line

    # A short refresh says how few calls it actually spent.
    assert "17 fetches attempted" in CrawlWorker._enrichment_log_line(17)


def test_the_benchmark_harness_exists_and_can_be_re_run():
    assert _TOOL.is_file(), "the enrichment benchmark is gone"
    text = _TOOL.read_text(encoding="utf-8")
    assert "enrich_datasets_with_inventory" in text
    assert "--markdown" in text
