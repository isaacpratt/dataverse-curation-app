"""Exception types shared across the client stack.

Control-flow signals, not failures: retry loops catch _RetryOriginal,
callers catch DownloadCancelled / GuestbookRequired.
"""

from curation.client.http import _error_message
from curation.client.refusals import refusal_code


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


def _with_refusal(entry: tuple[Exception, str, int]) -> Exception:
    """Attach the refusal code and the server's message to a refused read.

    The exception keeps its original type and response; the two extra
    attributes are what the dashboard shows ("not readable by this
    account") and what the Log explains.
    """
    exc, path, status = entry
    body = ""
    detail = ""
    try:
        resp = getattr(exc, "response", None)
        if resp is not None:
            body = str(resp.text or "")
            detail = _error_message(resp)
    except Exception:
        pass
    try:
        exc.refusal_code = refusal_code(path, status, body)  # type: ignore[attr-defined]
        exc.refusal_detail = detail  # type: ignore[attr-defined]
    except Exception:
        pass
    return exc
