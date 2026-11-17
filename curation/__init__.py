"""The curation core: configuration, client, local state and curation rules.

This package holds the application core - the parts that know about
Dataverse, the workspace and the curation rules - with no dependency on
the view layer (``ui/``) or on Qt. The view layer imports from here; the
core never imports the view (machine-enforced by import-linter, see
``poe contracts``).

Layout:

- ``curation.config``          - configuration load/save, env overrides, keyring
- ``curation.applog``          - in-memory request log with token redaction
- ``curation.storage``         - SQLite local state + JSON caches
- ``curation.download_manager``- approval-gated downloads, originals, verify
- ``curation.metadata_check``  - citation-block completeness (McMaster/Minimal)
- ``curation.review_rules``    - rule-driven completeness evaluation
- ``curation.response_draft``  - depositor response assembler
- ``curation.dashboard_cache`` - Qt-free dashboard cache helpers
- ``curation.client``          - the Dataverse Native/Search API client

``engine/`` (the check engine) and ``ui/`` (the PySide6 views) stay at the
repository root; ``main.py`` remains the single entry point for both the
GUI and ``--headless`` (ADR 0002, ADR 0006).
"""

from __future__ import annotations
