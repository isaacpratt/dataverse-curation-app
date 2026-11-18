"""Download orchestration for the Dataverse client.

_DownloadsMixin is mixed into DataverseClient; every method here relies on
the core session, retry and guestbook plumbing held in client.client. Kept
separate so client.client stays session/discovery-focused.
"""

import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from curation.applog import get_app_log
from curation.client.access import _mark_readable, _mark_restricted
from curation.client.constants import _RETRYABLE_NETWORK, _STREAM_CHUNK
from curation.client.errors import (
    DownloadCancelled,
    GuestbookRequired,
    _RetryOriginal,
    _with_refusal,
)
from curation.client.http import _error_message, _throttle_delay
from curation.client.parsers import (
    _summarize_version_data,
    _version_last_update,
    is_draft_dataset,
)
from curation.client.refusals import probe_skip_reason, version_probe_order


class _DownloadsMixin:
    # Attributes supplied by DataverseClient at construction/method scope;
    # declared here so mypy understands the mixin contract.
    _session: requests.Session
    _timeout: int
    _api_token: str
    _api: Callable[[str], str]
    _get_json: Callable[..., Any]

    def _fetch_version_data(
        self,
        identifier: str,
        version: str = "draft",
        fall_back_on_auth: bool = False,
        order: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Fetch the raw `data` payload for one dataset version.

        Tries `version` first (correct lowercase, e.g. `:draft`), then
        `:latest` / `:latest-published`, then an unversioned metadata read.
        Returns `(data, used_version, tried)`.

        `order` overrides that sequence with an explicit list of version
        specifiers — the dashboard enrichment passes the order derived from
        the search payload, so the app never asks for a version the search
        already ruled out (a :draft probe on a published dataset is always
        answered "not permitted"). An empty list means "probe no version":
        the unversioned dataset read answers with the version the account
        may see, in one call. `None` keeps the default sequence.

        With `fall_back_on_auth=False` (the default, used for the actual
        check inventory) an auth failure (401/403) fails fast — retrying
        other versions would mask a bad token and risk running checks on
        the wrong version silently.

        With `fall_back_on_auth=True` (dashboard enrichment) an auth
        failure on one version only means "you may not see that
        version" — a published dataset has no readable draft, and a
        guest token cannot see drafts at all. Enrichment then tries the
        next version. When EVERY version was refused, the unversioned
        dataset read decides: if that answers, the account can see the
        dataset but not its versions (an expected, version-scoped refusal);
        only a refusal there too means the dataset is out of reach.
        """
        tried: list[str] = []
        auth_errors: list[tuple[Exception, str, int]] = []
        candidates = list(order) if order is not None else [version, "latest", "latest-published"]
        for ver in candidates:
            api_version = ver if ver.startswith(":") else f":{ver.lower()}"
            vpath = (
                f"/api/datasets/:persistentId/versions/{api_version}"
                if ":" in identifier
                else f"/api/datasets/{identifier}/versions/{api_version}"
            )
            try:
                if ":" in identifier:
                    payload = self._get_json(
                        vpath,
                        params={"persistentId": identifier},
                    )
                else:
                    payload = self._get_json(vpath)
                return payload.get("data", {}), api_version, tried
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                status = resp.status_code if resp is not None else 0
                tried.append(f"{api_version}={status}")
                if status in (401, 403):
                    if not fall_back_on_auth:
                        # Auth failure: do not silently try other versions.
                        raise
                    # "You may not see this version" — remember it and try
                    # the next one.
                    auth_errors.append((exc, vpath, status))
                    get_app_log().info(
                        f"Version {api_version} not readable for {identifier} "
                        f"({status}), trying next version"
                    )
                    continue
                if status in (400, 404):
                    get_app_log().info(
                        f"Version {api_version} not available for {identifier} ({status}), trying next"
                    )
                    continue
                raise
        # Every version was refused (401/403). Before calling it a token
        # failure, try the unversioned read: the account may see the
        # dataset itself while every version of it stays out of reach —
        # that is an expected refusal, not a broken token.
        if auth_errors:
            try:
                payload = self._get_json(
                    "/api/datasets/:persistentId"
                    if ":" in identifier
                    else f"/api/datasets/{identifier}",
                    params={"persistentId": identifier} if ":" in identifier else None,
                )
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                status = resp.status_code if resp is not None else 0
                if status not in (401, 403):
                    raise
                # The dataset itself is out of reach for this account.
                raise _with_refusal(auth_errors[-1]) from None
            data = payload.get("data", {})
            return data, "unversioned", tried
        # fallback: try without version (latest published)
        payload = self._get_json(
            "/api/datasets/:persistentId" if ":" in identifier else f"/api/datasets/{identifier}",
            params={"persistentId": identifier} if ":" in identifier else None,
        )
        # dataset metadata contains latestVersion files? try to extract
        data = payload.get("data", {})
        return data, "unversioned", tried

    def enrich_datasets_with_inventory(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        datasets: list[dict[str, Any]],
        max_rows: int = 200,
        max_workers: int = 5,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        """Patch thin search rows with live inventory sums + depositor + state.

        For each row lacking `total_size_bytes`, fetches one version doc
        and patches `total_size_bytes` (summed), `file_count` (only when the
        search value is falsy), `depositor` (only when the version carries
        one), `state` (never clobbering an "In Review" lock confirmation),
        and `has_draft` (set True when the `:draft` doc answers). Patched
        rows get `size_enriched=True`; rows beyond `max_rows` keep thin
        data and get `size_pending=True` so the UI can say so. Never
        embeds file arrays — sums and counts only.

        The version probed comes from the search payload (see
        `version_probe_order`): the dataset read alone answers for a
        published or deaccessioned row (one call), and a row under
        curation is probed at `:draft` first, because that is the only
        version a curator cares about. Rows the account may not read are
        marked, not dropped: they carry an `access` fact with the machine
        reason code and the server's own message, so the dashboard can
        say why.

        Drafts go first so a capped run enriches curation candidates before
        published rows. Per-item isolation: one dataset's failure never
        fails the batch, and a refusal on one dataset never stops the
        others (the search call already proved the token works). Never
        raises; returns {"attempted", "enriched", "pending", "auth_failed",
        "restricted"}.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            rows = [d for d in (datasets or []) if isinstance(d, dict)]
        except Exception:
            return {
                "attempted": 0,
                "enriched": 0,
                "pending": 0,
                "auth_failed": 0,
                "restricted": 0,
            }
        candidates = [
            ds
            for ds in rows
            if ds.get("total_size_bytes") is None and str(ds.get("persistent_id") or "")
        ]
        # Drafts first: capped runs spend calls on curation candidates.
        try:
            candidates.sort(key=lambda ds: 0 if is_draft_dataset(ds) else 1)
        except Exception:
            pass
        todo = candidates[:max_rows] if max_rows >= 0 else list(candidates)
        for ds in candidates[len(todo) :]:
            try:
                if ds.get("total_size_bytes") is None:
                    ds["size_pending"] = True
            except Exception:
                pass
        result = {
            "attempted": 0,
            "enriched": 0,
            "pending": len(candidates) - len(todo),
            "auth_failed": 0,
            "restricted": 0,
        }
        if not todo:
            return result

        def _fetch_one(ds: dict[str, Any]) -> tuple[dict[str, Any], tuple[Any, ...]]:
            pid = str(ds.get("persistent_id") or "")
            # The search payload already says which versions can exist —
            # probe only those (a :draft probe on a published dataset is
            # always answered "not permitted").
            order = version_probe_order(ds)
            skip_reason = probe_skip_reason(ds)
            if skip_reason:
                get_app_log().info(f"Skipping version probes for {pid}: {skip_reason}")
            # fall_back_on_auth: a published dataset has no readable draft
            # and a guest token cannot see drafts at all — fall through to
            # the published version instead of failing the dataset.
            data, used_version, _tried = self._fetch_version_data(
                pid, fall_back_on_auth=True, order=order
            )
            files, depositor, state, files_known = _summarize_version_data(data)
            return ds, (
                files,
                depositor,
                state,
                used_version,
                files_known,
                _version_last_update(data),
            )

        def _auth_denied(exc: BaseException) -> bool:
            try:
                resp = getattr(exc, "response", None)
                return resp is not None and resp.status_code in (401, 403)
            except Exception:
                return False

        total = len(todo)
        done = 0
        try:
            with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
                futures = {pool.submit(_fetch_one, ds): ds for ds in todo}
                for fut in as_completed(futures):
                    if is_cancelled is not None:
                        try:
                            if is_cancelled():
                                for f in futures:
                                    f.cancel()
                                break
                        except Exception:
                            pass
                    ds = futures[fut]
                    result["attempted"] += 1
                    try:
                        _ds, summary = fut.result()
                    except Exception as exc:
                        if _auth_denied(exc):
                            # The dataset is out of reach for this account.
                            # That is an expected answer, not a broken
                            # token: mark the row and keep going.
                            _mark_restricted(ds, exc)
                            result["restricted"] += 1
                            continue
                        continue
                    try:
                        (
                            files,
                            depositor,
                            state,
                            used_version,
                            files_known,
                            last_update,
                        ) = summary
                        if last_update:
                            ds["draft_updated_at"] = last_update
                        if files_known:
                            ds["total_size_bytes"] = sum(
                                int(f.get("size_bytes") or 0) for f in files
                            )
                            ds["size_enriched"] = True
                            try:
                                ds.pop("size_pending", None)
                            except Exception:
                                pass
                            if not ds.get("file_count") and files:
                                ds["file_count"] = len(files)
                        if depositor and (
                            not ds.get("depositor") or ds.get("depositor") == ds.get("contact")
                        ):
                            ds["depositor"] = depositor
                        if state and "REVIEW" not in str(ds.get("state") or "").upper():
                            ds["state"] = state
                        if used_version == ":draft" or str(state or "").upper() == "DRAFT":
                            # The dataset read answers with the draft when
                            # the account may see it — that is a draft.
                            ds["has_draft"] = True
                        _mark_readable(ds, used_version, str(ds.get("state") or ""))
                        result["enriched"] += 1
                    except Exception:
                        continue
                    done += 1
                    if progress is not None:
                        try:
                            progress(done, total)
                        except Exception:
                            pass
        except Exception:
            pass
        return result

    # -- download ------------------------------------------------------------

    def _stream_url(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        url: str,
        params: dict[str, str],
        dl_headers: dict[str, str],
        dest: Path,
        progress: Callable[[int], None] | None,
        label: str,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> int | None:
        """Stream one URL to `dest`, with retries.

        Returns bytes received, or None when the server answers 400/404
        (version unavailable — caller tries the next version). Auth failures
        (401/403) raise immediately so a bad token is not masked by version
        fallback. Raises on persistent network/HTTP failure. `dest` is
        truncated at the start of every attempt, so callers must pass a
        .part path. `is_cancelled` is polled per chunk; a True answer
        raises DownloadCancelled, which is never retried.
        """
        from curation.applog import log_response

        if is_cancelled and is_cancelled():
            raise DownloadCancelled(label)
        for attempt in range(3):
            try:
                start = time.monotonic()
                with self._session.get(
                    url,
                    params=params,
                    headers=dl_headers,
                    stream=True,
                    timeout=self._timeout,
                ) as response:
                    if response.status_code in (401, 403):
                        get_app_log().error(
                            f"Download {label} denied ({response.status_code}) — "
                            "check API token, not trying other versions"
                        )
                        response.raise_for_status()
                    if response.status_code in (400, 404):
                        message = _error_message(response)
                        if "guestbook" in message.lower():
                            get_app_log().error(
                                f"Download {label} blocked by a guestbook requirement"
                            )
                            raise GuestbookRequired(
                                (message or "This dataset requires a Guestbook response.")
                                + " Reload the dataset metadata so the download "
                                "window can show the guestbook fields, then try again."
                            )
                        self._last_download_error = (
                            f"{message or 'The dataset or version was not found.'} "
                            f"(HTTP {response.status_code})"
                        )
                        get_app_log().info(
                            f"Download {label} not available ({response.status_code}): "
                            f"{message or 'no server message'}"
                        )
                        return None
                    log_response("GET", str(response.url), response.status_code, 0, "streaming…")
                    response.raise_for_status()
                    # Pre-flight disk-space check when the server advertises size.
                    try:
                        total_hdr = response.headers.get("Content-Length")
                        if total_hdr:
                            need = int(total_hdr)
                            free = __import__("shutil").disk_usage(str(dest.parent)).free
                            if need and free < need:
                                raise OSError(
                                    f"insufficient disk space for {label}: "
                                    f"need {need} bytes, {free} free"
                                )
                    except (TypeError, ValueError):
                        pass
                    received = 0
                    with open(dest, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=_STREAM_CHUNK):
                            if not chunk:
                                continue
                            if is_cancelled and is_cancelled():
                                raise DownloadCancelled(label)
                            handle.write(chunk)
                            received += len(chunk)
                            if progress:
                                try:
                                    progress(received)
                                except Exception:
                                    pass
                elapsed_ms = int((time.monotonic() - start) * 1000)
                get_app_log().info(f"Downloaded {received} bytes in {elapsed_ms} ms ({label})")
                return received
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                if resp is not None and resp.status_code in (401, 403):
                    raise
                if resp is not None and resp.status_code in (400, 404):
                    get_app_log().info(f"Download {label} failed ({resp.status_code}), trying next")
                    return None
                delay = _throttle_delay(exc)
                if delay is not None and attempt < 2:
                    wait = delay or 1.5 * (attempt + 1)
                    get_app_log().error(
                        f"Download {label} throttled, retrying in {wait:.1f}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait)
                    continue
                raise
            except _RETRYABLE_NETWORK as exc:
                get_app_log().error(
                    f"Download {label} network error (attempt {attempt + 1}/3): {exc}"
                )
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise requests.ConnectionError(
            f"Download {label} failed after 3 attempts"
        )  # pragma: no cover

    def _stream_download(
        self,
        path: str,
        params: dict[str, str],
        dl_headers: dict[str, str],
        dest: Path,
        progress: Callable[[int], None] | None,
        label: str,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> int | None:
        """Stream an API path (one version attempt) — see _stream_url."""
        return self._stream_url(
            self._api(path), params, dl_headers, dest, progress, label, is_cancelled
        )

    def _guestbook_signed_url(self, identifier: str, guestbook_response: dict[str, Any]) -> str:
        """POST a guestbook response and return Dataverse's signed download URL.

        Dataverse never streams the bundle for a guestbook-protected dataset
        directly: POSTing the answers records the response and answers with
        ``{"data": {"signedUrl": "..."}}``; the signed URL then streams the
        ZIP (it carries ``gbrecs=true``/``gbrids=...``). The POST requires an
        API token, so a guestbook cannot be answered without one.
        """
        if not self._api_token:
            raise requests.HTTPError(
                "This dataset requires a guestbook response, which needs a "
                "Dataverse API token. Add one in Settings (Ctrl+,)."
            )
        by_pid = ":" in identifier
        path = (
            "/api/access/dataset/:persistentId" if by_pid else f"/api/access/dataset/{identifier}"
        )
        params = {"persistentId": identifier} if by_pid else {}
        headers = {
            "X-Dataverse-key": self._api_token,
            "Content-Type": "application/json",
        }
        response = self._session.post(
            self._api(path),
            params=params,
            headers=headers,
            json={"guestbookResponse": guestbook_response or {}},
            timeout=self._timeout,
        )
        try:
            if response.status_code == 400:
                message = _error_message(response)
                raise requests.HTTPError(
                    "Dataverse rejected the guestbook response: "
                    + (message or "a required answer is missing.")
                )
            response.raise_for_status()
            payload = response.json()
        finally:
            try:
                response.close()
            except Exception:
                pass
        data = payload.get("data") if isinstance(payload, dict) else None
        signed = data.get("signedUrl") if isinstance(data, dict) else None
        if not signed:
            raise requests.HTTPError(
                "Dataverse accepted the guestbook response but returned no "
                "download link. Try downloading from the dataset's web page."
            )
        get_app_log().info("Guestbook accepted — streaming the signed download URL")
        return str(signed)

    def download_dataset_zip(
        self,
        identifier: str,
        dest: Path,
        version: str = "draft",
        progress: Callable[[int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        guestbook_response: dict[str, Any] | None = None,
    ) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Access API expects plain version name (draft/latest) without colon; keep original case for dataset.xhtml but API is lower
        # Use Accept: */* for zip download (application/json causes 406)
        dl_headers = {}
        if self._api_token:
            dl_headers["X-Dataverse-key"] = self._api_token
        access_version = version.lstrip(":").lower()
        by_pid = ":" in identifier
        self._last_download_error = ""
        if guestbook_response is not None:
            # Answering the guestbook is a separate exchange: POST the answers,
            # then stream the signed URL. Version fallback does not apply (the
            # POST endpoint already picks the draft when the token may see it).
            signed_url = self._guestbook_signed_url(identifier, guestbook_response)
            if (
                self._stream_url(signed_url, {}, {}, dest, progress, "guestbook", is_cancelled)
                is not None
            ):
                return dest
            detail = getattr(self, "_last_download_error", "") or "the bundle was not found"
            raise requests.HTTPError(f"Dataset bundle download failed: {detail}.")
        # Try requested version, fall back to latest if not found
        for ver in (access_version, "latest"):
            params = {"persistentId": identifier, "version": ver} if by_pid else {"version": ver}
            path = (
                "/api/access/dataset/:persistentId"
                if by_pid
                else f"/api/access/dataset/{identifier}"
            )
            if (
                self._stream_download(
                    path, params, dl_headers, dest, progress, f"version {ver}", is_cancelled
                )
                is not None
            ):
                return dest
        # final attempt without version
        path = (
            "/api/access/dataset/:persistentId" if by_pid else f"/api/access/dataset/{identifier}"
        )
        params = {"persistentId": identifier} if by_pid else {}
        if (
            self._stream_download(
                path, params, dl_headers, dest, progress, "unversioned", is_cancelled
            )
            is None
        ):
            detail = (
                getattr(self, "_last_download_error", "") or "the dataset or version was not found"
            )
            raise requests.HTTPError(
                f"Dataset bundle download failed: {detail}. Check that the dataset "
                "exists on this Dataverse and that the API token can access it."
            )
        return dest

    def download_datafile_original(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        file_id: str,
        dest: Path,
        progress: Callable[[int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Download one file in its ORIGINAL uploaded format.

        Tabular ingests are served as generated .tab by default; passing
        ?format=original returns the depositor's upload (e.g. .sav). Raises
        RuntimeError when unavailable so callers can skip the file.
        `is_cancelled` is polled before each attempt and per chunk; a True
        answer raises DownloadCancelled, which is never retried.
        """
        from curation.applog import log_response

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dl_headers: dict[str, str] = {"Accept": "*/*"}
        if self._api_token:
            dl_headers["X-Dataverse-key"] = self._api_token
        if is_cancelled and is_cancelled():
            raise DownloadCancelled(f"datafile {file_id}")
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                with self._session.get(
                    self._api(f"/api/access/datafile/{file_id}"),
                    params={"format": "original"},
                    headers=dl_headers,
                    stream=True,
                    timeout=self._timeout,
                ) as response:
                    if response.status_code in (400, 401, 403, 404):
                        raise RuntimeError(
                            f"original format unavailable for file {file_id} "
                            f"({response.status_code})"
                        )
                    log_response(
                        "GET", str(response.url), response.status_code, 0, "streaming original…"
                    )
                    try:
                        response.raise_for_status()
                    except requests.HTTPError as http_exc:
                        # Honor Retry-After on throttle / transient overload.
                        delay = _throttle_delay(http_exc)
                        if delay is not None and attempt < 2:
                            wait = delay or 1.5 * (attempt + 1)
                            get_app_log().error(
                                f"GET datafile/{file_id} throttled, retrying in "
                                f"{wait:.1f}s (attempt {attempt + 1}/3)"
                            )
                            time.sleep(wait)
                            # Retry without truncating a prior partial twice:
                            # loop re-opens dest with "wb".
                            raise _RetryOriginal() from None
                        raise
                    received = 0
                    with open(dest, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=_STREAM_CHUNK):
                            if not chunk:
                                continue
                            if is_cancelled and is_cancelled():
                                raise DownloadCancelled(f"datafile {file_id}")
                            handle.write(chunk)
                            received += len(chunk)
                            if progress:
                                try:
                                    progress(received)
                                except Exception:
                                    pass
                elapsed_ms = int((time.monotonic() - start) * 1000)
                get_app_log().info(f"Downloaded original ({received} bytes) in {elapsed_ms} ms")
                return dest
            except RuntimeError:
                raise
            except _RetryOriginal:
                last_exc = RuntimeError("throttled")
                continue
            except _RETRYABLE_NETWORK as exc:
                last_exc = exc
                get_app_log().error(
                    f"GET datafile/{file_id} network error (attempt {attempt + 1}/3): {exc}"
                )
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"original-format download failed for file {file_id}: {exc}"
                ) from exc
        assert last_exc is not None
        raise RuntimeError(f"original-format download failed for file {file_id}: {last_exc}")

    @staticmethod
    def hash_file(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_STREAM_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()
