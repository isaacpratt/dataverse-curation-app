"""External-link check for the published documentation.

Network checks are deliberately kept out of the per-PR gate: a third-party
site being down must not fail a docs change. This script runs on a weekly
schedule and on demand (``.github/workflows/docs-links.yml``), so a dead link
is reported without making flaky network access part of CI.

Usage::

    uv run python tools/docs/check_external_links.py [--timeout 15]

Exit 0 when every URL responds, 1 when one fails, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

DOCS = Path(__file__).resolve().parents[2] / "docs"
EXTRA = (Path(__file__).resolve().parents[2] / "README.md",)
URL_RE = re.compile(r"https?://[^\s)<>\]\"']+")
FENCE_RE = re.compile(r"^(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
USER_AGENT = (
    "DataverseDocent-docs-linkcheck/1.0 (+https://github.com/isaacpratt/dataverse-curation-app)"
)


def external_urls(paths: tuple[Path, ...] = ()) -> list[str]:
    """Every http(s) URL in the docs and README, de-duplicated and sorted."""
    files = sorted(DOCS.rglob("*.md")) + list(EXTRA) if not paths else list(paths)
    urls: set[str] = set()
    for path in files:
        if not path.is_file():
            continue
        in_fence = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if FENCE_RE.match(line.strip()):
                in_fence = not in_fence
            if in_fence:
                continue
            for url in URL_RE.findall(INLINE_CODE_RE.sub("", line)):
                # Markdown punctuation often follows a bare URL (a closing
                # backtick, a bold marker, a sentence period).
                url = url.rstrip(".,;:`*_~")
                if re.match(r"^https?://[^\s/?#]+", url):
                    urls.add(url)
    return sorted(urls)


def check_url(url: str, timeout: float, session: requests.Session) -> tuple[bool, str]:
    """HEAD first (with a GET fallback for servers that reject HEAD)."""
    try:
        response = session.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400:
            response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        return response.status_code < 400, str(response.status_code)
    except requests.RequestException as exc:
        return False, type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    """Check every external URL found in the documentation."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, default=15.0, help="per-request timeout (seconds)")
    args = parser.parse_args(argv)
    if not DOCS.is_dir():
        print(f"docs-links: {DOCS} not found", file=sys.stderr)
        return 2

    urls = external_urls()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    failed: list[str] = []
    for url in urls:
        ok, detail = check_url(url, args.timeout, session)
        print(f"{'OK  ' if ok else 'FAIL'} {detail:>8}  {url}")
        if not ok:
            failed.append(url)
    print(f"external-links: {len(urls) - len(failed)}/{len(urls)} URLs reachable")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
