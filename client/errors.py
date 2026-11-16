"""Exception types shared across the client stack.

Control-flow signals, not failures: retry loops catch _RetryOriginal,
callers catch DownloadCancelled / GuestbookRequired.
"""


class _RetryOriginal(Exception):  # noqa: N818 - internal control-flow signal, never crosses the API surface
    """Internal: throttled original-format download should retry the loop."""


class DownloadCancelled(Exception):  # noqa: N818 - public API name; renaming breaks existing callers
    """Raised from a streaming loop when the curator cancels the download.

    Deliberately not an HTTP/network error: the retry loops must never
    catch or replay it — it propagates straight through DownloadManager
    to the worker, which turns it into the `cancelled` signal.
    """


class GuestbookRequired(Exception):  # noqa: N818 - public API name; renaming breaks existing callers
    """The Access API refused the bundle because a guestbook must be answered.

    Dataverse answers HTTP 400 ("You may not download this file without the
    required Guestbook response ..."), which must not be mistaken for a
    missing version: no retry or version fallback can succeed until the
    guestbook is answered. Deliberately not an HTTPError so the streaming
    retry loop does not swallow it as an unavailable version.
    """
