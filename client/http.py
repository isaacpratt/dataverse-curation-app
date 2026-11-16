"""HTTP helpers for the Dataverse client stack."""

import requests

from client.constants import _RETRYABLE_STATUS


def _error_message(response) -> str:
    """Best-effort Dataverse error message from a JSON error response."""
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if message:
            return str(message).strip()
    try:
        return (response.text or "").strip()[:400]
    except Exception:
        return ""


def _throttle_delay(exc: requests.HTTPError) -> float | None:
    """Retry-After seconds for a retryable HTTP error, else None.

    Returns 0.0 when the status is retryable but carries no usable
    Retry-After header (caller falls back to linear backoff).
    """
    resp = getattr(exc, "response", None)
    if resp is None or resp.status_code not in _RETRYABLE_STATUS:
        return None
    try:
        return max(0.0, min(30.0, float(resp.headers.get("Retry-After", ""))))
    except (TypeError, ValueError):
        return 0.0
