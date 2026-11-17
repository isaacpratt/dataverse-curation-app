"""Shared retry/streaming constants for the Dataverse client.

State token for the review lock and the retry/backoff pools; no
behaviour of its own.
"""

import requests

_STREAM_CHUNK = 1 << 20

# Canonical state token for "locked for review". This is a *data* contract
# shared by the client, the engine and the dashboard cache — not interface
# copy, so it is deliberately not translated. The GUI renders it through its
# own display-state mapping (``dashboard.display_state.review``).
STATE_IN_REVIEW = "In Review"

# Network failures worth one retry cycle (timeouts included: a stalled
# bundle stream otherwise restarts from zero with no second chance).
_RETRYABLE_NETWORK = (
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.Timeout,
    ConnectionResetError,
)

# HTTP statuses worth retrying (throttle / transient overload).
_RETRYABLE_STATUS = (429, 503)

# Refusal classification substrings (used by _refusal / expected_api_reason).
_REFUSAL_VERSIONS = "/versions/"
_REFUSAL_COMPARE = "/compare/"

# Version specifiers probed for one dataset, in the order the app asks.
_VERSION_DRAFT = ":draft"
_VERSION_PUBLISHED = ":latest-published"
_VERSION_LATEST = ":latest"
