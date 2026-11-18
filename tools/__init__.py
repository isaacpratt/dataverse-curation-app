"""Operational helpers that run outside the app (build, audit, docs, probes).

They are not imported by the application at runtime; `main.py` and the
frozen build never load them. Tests for these scripts live in `tools/tests/`.
"""
