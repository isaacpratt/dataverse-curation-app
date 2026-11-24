"""Dataverse Native API client - session and discovery core.

Owns the HTTP session, pagination/discovery plumbing and error handling.
Payload parsing lives in client.parsers; identity/labels/metadatablock
caching in client.caches; download/guestbook/streaming orchestration in
client.downloads (mixed into DataverseClient below). See
docs/html/dataverse-integration.html for endpoints and auth.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from curation.applog import get_app_log
from curation.client import caches as _caches
from curation.client.caches import (
    _me_cache_key,
    get_cached_allowed_labels,
    get_cached_metadata_fields,
    set_cached_allowed_labels,
    set_cached_metadata_fields,
)
from curation.client.constants import _RETRYABLE_NETWORK
from curation.client.downloads import _DownloadsMixin
from curation.client.http import _error_message, _throttle_delay
from curation.client.parsers import (
    _version_files_data,
    locks_indicate_review,
    normalize_files,
    note_review_submission,
    parse_allowed_labels,
    parse_curation_states_csv,
    parse_curation_status,
    parse_dataset_versions,
    parse_metadatablock_display_names,
    parse_metadatablock_fields,
    parse_metadatablock_names,
    parse_timestamps,
    parse_version_compare,
    search_item_state,
)
from curation.client.refusals import expected_api_reason, refusal_code
from curation.config import normalise_base_url


class DataverseClient(_DownloadsMixin):
    def __init__(self, base_url: str, api_token: str, timeout: int = 120) -> None:
        # Defence in depth: callers normally come through Config (which
        # validates), but workers build clients from their own copies of the
        # URL and the token is sent in a header on every request.
        self._base_url = normalise_base_url(base_url)
        self._api_token = api_token
        self._timeout = timeout
        # A requests.Session is not thread-safe, and this client is shared by
        # the enrichment, lock-probe and detail-fetch pools. Give each thread
        # its own session so connection reuse stays per-thread and no two
        # threads touch the same pool. Tests may assign a fake session, which
        # then acts as an override for every thread.
        self._session_override: requests.Session | None = None
        self._local = threading.local()
        self._all_sessions: list[requests.Session] = []
        # Probe-round bookkeeping for allowedCurationLabels (see
        # get_allowed_curation_labels / fetch_allowed_labels_shared):
        # _last_allowed_got_200 tracks the latest single attempt,
        # _last_fetch_answered aggregates the latest shared round.
        self._last_allowed_got_200 = False
        self._last_fetch_answered = False

    @property
    def _session(self) -> requests.Session:
        if self._session_override is not None:
            return self._session_override
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            try:
                from requests.adapters import HTTPAdapter

                adapter = HTTPAdapter(pool_connections=4, pool_maxsize=16)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
            except Exception:
                pass
            self._local.session = session
            self._all_sessions.append(session)
        return session

    @_session.setter
    def _session(self, value: requests.Session) -> None:
        self._session_override = value

    def close(self) -> None:
        # Tests may construct via __new__ with only a fake session.
        sessions = list(getattr(self, "_all_sessions", []))
        override = getattr(self, "_session_override", None)
        if override is not None:
            sessions.append(override)
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

    # -- low level -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_token:
            headers["X-Dataverse-key"] = self._api_token
        return headers

    def _api(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        from curation.applog import log_response

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                response = self._session.get(
                    self._api(path),
                    params=params,
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                summary = ""
                body: dict[str, Any] | None = None
                if response.ok:
                    try:
                        body = response.json()
                    except ValueError:
                        # Non-JSON 200 (e.g. HTML error page): surface body
                        # snippet instead of raw JSONDecodeError.
                        get_app_log().error(
                            f"GET {response.url} → {response.status_code}: "
                            f"non-JSON response: {response.text[:300]}"
                        )
                        response.raise_for_status()
                        raise RuntimeError(
                            f"GET {path} returned non-JSON response ({response.status_code})"
                        ) from None
                    if path == "/api/search" and isinstance(body, dict):
                        try:
                            n = len(body.get("data", {}).get("items", []))
                        except Exception:
                            n = 0
                        summary = f"{n} item(s)" if n else ""
                status = response.status_code
                # Some endpoints answer 4xx by design (a draft this account
                # may not read, a dataset with no published version). The
                # call and the response are logged verbatim either way —
                # only the severity and the added context differ.
                reason = expected_api_reason(path, status, response.text)
                log_response(
                    "GET",
                    str(response.url),
                    status,
                    elapsed_ms,
                    summary,
                    context=reason,
                )
                if not response.ok:
                    body_text = response.text[:300]
                    if reason:
                        get_app_log().expected(
                            f"GET {response.url} → {status}: {body_text} — {reason}"
                        )
                    else:
                        get_app_log().error(f"GET {response.url} → {status}: {body_text}")
                response.raise_for_status()
                # Reuse already-parsed body when available.
                if body is not None:
                    return body
                parsed: dict[str, Any] = response.json()
                return parsed
            except requests.HTTPError as exc:
                delay = _throttle_delay(exc)
                if delay is not None and attempt < 2:
                    wait = delay or 1.5 * (attempt + 1)
                    get_app_log().error(
                        f"GET {path} throttled, retrying in {wait:.1f}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait)
                    continue
                raise
            except _RETRYABLE_NETWORK as exc:
                last_exc = exc
                get_app_log().error(f"GET {path} network error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise requests.ConnectionError(
                    f"{exc} — the remote host closed the connection. "
                    "Try again; if it persists check your VPN/proxy or that "
                    f"{self._base_url} is reachable."
                ) from exc
            except Exception as exc:
                get_app_log().error(f"GET {path} failed: {exc}")
                raise
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    def _get_text(self, path: str, params: dict[str, str] | None = None) -> str:
        """GET returning raw text (for non-JSON endpoints like the CSV report).

        Same retry/logging contract as _get_json, except the Accept header
        advertises text/csv: the CSV report endpoint answers 406 when asked
        for application/json. HTTP errors propagate so callers can
        distinguish 403 (no permission) from other failures.
        """
        from curation.applog import log_response

        headers = {"Accept": "text/csv, */*"}
        if self._api_token:
            headers["X-Dataverse-key"] = self._api_token
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                response = self._session.get(
                    self._api(path),
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                summary = ""
                if response.ok:
                    summary = f"{len(response.content)} byte(s)"
                status = response.status_code
                reason = expected_api_reason(path, status, response.text)
                log_response(
                    "GET",
                    str(response.url),
                    status,
                    elapsed_ms,
                    summary,
                    context=reason,
                )
                if not response.ok:
                    body = response.text[:300]
                    if reason:
                        get_app_log().expected(f"GET {response.url} → {status}: {body} — {reason}")
                    else:
                        get_app_log().error(f"GET {response.url} → {status}: {body}")
                response.raise_for_status()
                return str(response.text)
            except requests.HTTPError as exc:
                delay = _throttle_delay(exc)
                if delay is not None and attempt < 2:
                    wait = delay or 1.5 * (attempt + 1)
                    get_app_log().error(
                        f"GET {path} throttled, retrying in {wait:.1f}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait)
                    continue
                raise
            except _RETRYABLE_NETWORK as exc:
                last_exc = exc
                get_app_log().error(f"GET {path} network error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise requests.ConnectionError(
                    f"{exc} — the remote host closed the connection. "
                    "Try again; if it persists check your VPN/proxy or that "
                    f"{self._base_url} is reachable."
                ) from exc
            except Exception as exc:
                get_app_log().error(f"GET {path} failed: {exc}")
                raise
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    # -- discovery -----------------------------------------------------------

    def _search_page(
        self, subtree: str = "", per_page: int = 100, start: int = 0
    ) -> tuple[list[dict[str, Any]], int | None]:
        """One Search API page → (rows, total_count).

        `total_count` is the server's total match count (None when the
        server omits it). Rows carry only what a Solr search doc has:
        no byte totals, no inventory.
        """
        params: dict[str, str] = {
            "q": "*",
            "type": "dataset",
            "per_page": str(per_page),
            "start": str(start),
        }
        subtree = (subtree or "").strip()
        if subtree and subtree.lower() not in ("root", ":root"):
            params["subtree"] = subtree
        get_app_log().info(
            f"Search API q=* type=dataset per_page={per_page} start={start} subtree='{subtree}'"
        )
        try:
            payload = self._get_json("/api/search", params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 404):
                body = ""
                try:
                    body = resp.json().get("message", "") or resp.text[:500]
                except Exception:
                    body = resp.text[:500] if hasattr(resp, "text") else ""
                raise RuntimeError(
                    f"Collection '{subtree}' not found or not accessible"
                    + (f": {body}" if body else "")
                    + " — try an empty alias for the whole repository, or check the alias spelling."
                ) from exc
            raise
        data_block = payload.get("data", {}) or {}
        items = data_block.get("items", [])
        try:
            total_count: int | None = int(data_block["total_count"])
        except (KeyError, TypeError, ValueError):
            total_count = None
        datasets: list[dict[str, Any]] = []
        for item in items:
            pid = item.get("global_id") or item.get("identifier") or ""
            contacts = item.get("contacts") or []
            contact = ", ".join(c.get("name", "") for c in contacts[:2] if c.get("name"))
            collection = item.get("name_of_dataverse") or item.get("identifier_of_dataverse") or ""
            if item.get("identifier_of_dataverse") and item.get("name_of_dataverse"):
                collection = f"{item['name_of_dataverse']} ({item['identifier_of_dataverse']})"
            # depositor not directly in search; use contact as fallback until detail is loaded
            state, has_draft = search_item_state(item)
            datasets.append(
                {
                    "persistent_id": pid,
                    "title": item.get("name") or item.get("title") or pid,
                    "contact": contact,
                    "depositor": contact,
                    "date_created": (item.get("createdAt") or "")[:10],
                    "date_published": (item.get("published_at") or "")[:10],
                    "collection": collection,
                    "state": state,
                    "has_draft": has_draft,
                    "publication_statuses": [
                        str(s or "") for s in (item.get("publicationStatuses") or [])
                    ],
                    "file_count": int(item.get("fileCount") or 0),
                    # Search items carry no byte totals — None (unknown, shown
                    # as "—") rather than a misleading 0. The enrichment
                    # stage and the download quote provide real sums.
                    "total_size_bytes": None,
                    "files": [],
                }
            )
        return datasets, total_count

    def _search_fallback(
        self, subtree: str = "", per_page: int = 100, start: int = 0
    ) -> list[dict[str, Any]]:
        """One Search API page as rows only (compat wrapper)."""
        rows, _total = self._search_page(subtree, per_page, start)
        return rows

    def list_draft_datasets(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self,
        subtree: str = "",
        per_page: int = 1000,
        max_pages: int = 100,
        progress: Callable[[int, int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """All datasets in the subtree (superset of in-review).

        Pages the native Search API with `per_page` (1000 by default) and
        drives the loop from the server's `total_count`: the page count is
        known after the first response, so progress can be reported as
        "page N of M". Termination is belt-and-suspenders — the loop ends
        when the collected count reaches the total, when a page comes back
        short or empty (the ground truth for a corpus that shifts under a
        long crawl), or when the runaway guard trips. Whatever ends it, the
        collected count is reconciled against the total and any gap is
        logged loudly instead of pretending the pull was complete.

        `max_pages` is a runaway guard (100 × 1000 = 100k datasets), not a
        data cap. `progress(page, pages_total, collected)` is called after
        each page; `is_cancelled` stops the crawl cooperatively.
        """
        all_datasets: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        total_expected: int | None = None
        pages_total: int | None = None
        hit_page_cap = False
        page = 0
        while page < max_pages:
            if is_cancelled is not None:
                try:
                    if is_cancelled():
                        break
                except Exception:
                    pass
            page += 1
            start = (page - 1) * per_page
            batch, total_count = self._search_page(subtree, per_page, start)
            if total_count is not None and total_expected is None:
                total_expected = total_count
                try:
                    pages_total = max(1, -(-total_expected // per_page))
                except Exception:
                    pages_total = None
            if not batch:
                get_app_log().info(f"Search page {page} (start={start}): empty — stopping")
                break
            new = 0
            dupes = 0
            for d in batch:
                pid = d["persistent_id"]
                if pid not in seen:
                    seen[pid] = len(all_datasets)
                    all_datasets.append(d)
                    new += 1
                else:
                    # The same dataset twice in the index (a published doc
                    # and a draft doc for it). The search total counts
                    # documents, not datasets — these are not missing rows.
                    dupes += 1
                if (
                    d.get("has_draft")
                    and pid in seen
                    and not all_datasets[seen[pid]].get("has_draft")
                ):
                    # Same dataset surfaced twice (published doc shadows the
                    # draft doc): keep the draft row so in-progress versions
                    # stay visible to draft filtering.
                    all_datasets[seen[pid]] = d
                    new += 1
            get_app_log().info(
                f"Search page {page} (start={start}): {len(batch)} item(s), "
                f"{new} new, cumulative {len(all_datasets)}"
            )
            if progress is not None:
                try:
                    progress(page, pages_total or 0, len(all_datasets))
                except Exception:
                    pass
            if len(batch) < per_page:
                # Short page: the corpus is exhausted (or the server
                # clamped per_page). Ground truth — stop here.
                break
            if total_expected is not None and len(all_datasets) >= total_expected:
                # Reached the advertised total: the plan is done. The
                # short-page rule above covers a corpus that grew.
                break
            if page == max_pages:
                hit_page_cap = True
        if hit_page_cap:
            get_app_log().error(
                f"Search hit the {max_pages}-page runaway guard — results are "
                "TRUNCATED. Narrow the collection/subtree and refresh."
            )
        # Reconcile what we got against what the server advertised.
        if total_expected is not None and len(all_datasets) != total_expected:
            gap = total_expected - len(all_datasets)
            if gap > 0:
                if dupes >= gap:
                    # The search index counts documents, not datasets: one
                    # dataset can be listed twice (its published doc and its
                    # draft doc). Those were merged — nothing is missing.
                    get_app_log().info(
                        f"Search collected {len(all_datasets)} of {total_expected} "
                        f"dataset(s) — {dupes} duplicate document(s) for the same "
                        "dataset (published and draft) were merged; nothing is missing"
                    )
                else:
                    get_app_log().error(
                        f"Search collected {len(all_datasets)} of {total_expected} "
                        f"dataset(s) — {gap} missing (the index changed during the "
                        "crawl, or the server clamps page size). Narrow the "
                        "collection and refresh if rows are missing."
                    )
            else:
                get_app_log().info(
                    f"Search collected {len(all_datasets)} dataset(s) — "
                    f"{abs(gap)} more than the advertised total of "
                    f"{total_expected} (the index grew during the crawl)"
                )
        get_app_log().info(
            f"Search complete: {len(all_datasets)} dataset(s)"
            f"{' (TRUNCATED — see above)' if hit_page_cap else ''}"
        )
        return all_datasets

    def dataset_in_review(self, identifier: str) -> bool:
        try:
            if ":" in identifier:
                payload = self._get_json(
                    "/api/datasets/:persistentId/locks",
                    params={"persistentId": identifier},
                )
            else:
                payload = self._get_json(f"/api/datasets/{identifier}/locks")
            return locks_indicate_review(payload.get("data", []))
        except (
            requests.HTTPError,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            return False

    def list_datasets_in_review(self, subtree: str = "") -> list[dict[str, Any]]:
        """Drafts from the crawl, kept only when locked IN_REVIEW."""
        drafts = self.list_draft_datasets(subtree)
        return [d for d in drafts if self.dataset_in_review(d["persistent_id"])]

    # -- authenticated identity --------------------------------------------
    # GET /api/users/:me answers for ANY valid token with the caller's
    # profile, including the `superuser` flag. Used to pick the superuser
    # vs curator code path (bulk CSV report vs per-draft label reads) once
    # per session instead of burning a doomed 403 first.

    def get_me(self) -> dict[str, Any] | None:
        """Fetch the authenticated user's profile (identity + superuser flag), or None.

        One network call per (instance, token) per process: successes are
        cached; failures return None without caching (a later retry may
        succeed). Never raises.
        """
        key = _me_cache_key(self._base_url, self._api_token)
        try:
            with _caches._ME_LOCK:
                hit = _caches._ME_CACHE.get(key)
            if isinstance(hit, dict):
                return dict(hit)
        except Exception:
            pass
        try:
            payload = self._get_json("/api/users/:me")
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            status = resp.status_code if resp is not None else 0
            if status in (400, 401, 403, 404):
                try:
                    get_app_log().info(
                        f"users/:me unavailable (HTTP {status}) — continuing without identity"
                    )
                except Exception:
                    pass
                return None
            raise
        except _RETRYABLE_NETWORK as exc:
            try:
                get_app_log().info(f"users/:me network error — continuing without identity ({exc})")
            except Exception:
                pass
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        try:
            with _caches._ME_LOCK:
                _caches._ME_CACHE[key] = dict(data)
        except Exception:
            pass
        return dict(data)

    def user_is_superuser(self) -> bool | None:
        """True/False from /api/users/:me; None when identity is unknown."""
        try:
            me = self.get_me()
        except Exception:
            return None
        if not isinstance(me, dict):
            return None
        return bool(me.get("superuser"))

    def get_collection_roles(self, alias: str) -> list[str] | None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        """Role names the calling user holds on one collection, or None.

        Matches the /api/users/:me identifier against
        GET /api/dataverses/{alias}/assignments (e.g. "@pratti" -> Admin).
        Cached per (instance, token, alias); denials and network failures
        return None without caching. Never raises for 4xx/network; other
        HTTP errors propagate like the other client methods.
        """
        alias = (alias or "").strip()
        if not alias:
            return None
        key = (*_me_cache_key(self._base_url, self._api_token), alias.lower())
        try:
            with _caches._ME_LOCK:
                hit = _caches._ROLE_CACHE.get(key)
            if isinstance(hit, list):
                return list(hit)
        except Exception:
            pass
        try:
            me = self.get_me()
        except Exception:
            return None
        identifier = str((me or {}).get("identifier") or "").strip()
        if not identifier:
            return None
        try:
            from urllib.parse import quote as _quote

            payload = self._get_json(f"/api/dataverses/{_quote(alias, safe='')}/assignments")
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            status = resp.status_code if resp is not None else 0
            if status in (400, 401, 403, 404):
                try:
                    get_app_log().info(
                        f"assignments for '{alias}' unavailable (HTTP {status}) — "
                        "continuing without collection role"
                    )
                except Exception:
                    pass
                return None
            raise
        except _RETRYABLE_NETWORK as exc:
            try:
                get_app_log().info(
                    f"assignments for '{alias}' network error — "
                    f"continuing without collection role ({exc})"
                )
            except Exception:
                pass
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return None
        roles: list[str] = []
        for entry in data:
            try:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("assignee") or "").strip() != identifier:
                    continue
                name = str(entry.get("roleName") or entry.get("_roleAlias") or "").strip()
                if name and name not in roles:
                    roles.append(name)
            except Exception:
                continue
        try:
            with _caches._ME_LOCK:
                _caches._ROLE_CACHE[key] = list(roles)
        except Exception:
            pass
        return roles

    # -- curation labels ---------------------------------------------------
    # See https://guides.dataverse.org/en/latest/api/curation-labels.html
    # Labels are configured per Dataverse instance/collection (AllowedCurationLabels),
    # so the allowed set can differ between instances. All methods degrade to
    # None/[] when labels are not configured or the caller lacks permission
    # (403/404), never raising for those cases.

    def _curation_paths(self, identifier: str, endpoint: str) -> tuple[str, dict[str, str] | None]:
        if ":" in identifier:
            return (
                f"/api/datasets/:persistentId/{endpoint}",
                {"persistentId": identifier},
            )
        return f"/api/datasets/{identifier}/{endpoint}", None

    def get_curation_status(
        self,
        identifier: str,
        include_history: bool = False,
        refusal: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return the current curation label for a draft dataset, or None if unset/unavailable.

        `refusal` is an optional dict the caller passes in; when the server
        refuses the read it is filled with {"status", "code", "detail"} so
        the dashboard can say why a dataset has no curation state instead
        of showing an empty column.
        """
        path, base_params = self._curation_paths(identifier, "curationStatus")
        params = dict(base_params or {})
        if include_history:
            params["includeHistory"] = "true"
        try:
            payload = self._get_json(path, params=params or None)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                if refusal is not None:
                    try:
                        body = str(resp.text or "")
                        refusal.update(
                            {
                                "status": int(resp.status_code),
                                "code": refusal_code(path, resp.status_code, body),
                                "detail": _error_message(resp),
                            }
                        )
                    except Exception:
                        pass
                return None
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            return None
        return parse_curation_status(payload)

    def get_curation_history(self, identifier: str) -> list[dict[str, Any]]:
        """Full label-assignment history (oldest-first) for a draft dataset."""
        path, base_params = self._curation_paths(identifier, "curationStatus")
        params = dict(base_params or {})
        params["includeHistory"] = "true"
        try:
            payload = self._get_json(path, params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                return []
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            return []
        data = (payload or {}).get("data")
        if not isinstance(data, list):
            single = parse_curation_status(payload)
            return [single] if single else []
        out = []
        for entry in data:
            if isinstance(entry, dict) and str(entry.get("label") or "").strip():
                out.append(
                    {
                        "label": str(entry.get("label")).strip(),
                        "time": str(entry.get("createTime") or ""),
                        "assigner": str(entry.get("assigner") or entry.get("user") or ""),
                    }
                )
        return out

    def get_allowed_curation_labels(self, identifier: str) -> list[str]:
        """Return allowed labels for one dataset (instance/collection-specific).

        Reports what the server answered to the app log: the received list
        on success, or the denial status when this dataset yields no answer
        (403/404/400 = no PublishDataset permission or not a draft — the
        caller probes further datasets in that case).
        """
        path, params = self._curation_paths(identifier, "allowedCurationLabels")
        try:
            payload = self._get_json(path, params=params)
            # A 200 answer (even an empty allowed set) is a DEFINITIVE
            # server answer — recorded so callers can tell "the server
            # said nothing is configured" apart from transport/server
            # errors, which must never freeze an empty cache in place.
            try:
                self._last_allowed_got_200 = True
            except Exception:
                pass
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            status = resp.status_code if resp is not None else 0
            if status in (400, 401, 403, 404):
                try:
                    get_app_log().info(
                        f"allowedCurationLabels for {identifier}: HTTP {status} — "
                        "no answer from this dataset"
                    )
                except Exception:
                    pass
                return []
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            try:
                get_app_log().info(
                    f"allowedCurationLabels for {identifier}: network error — no answer"
                )
            except Exception:
                pass
            return []
        labels = parse_allowed_labels(payload.get("data"))
        try:
            get_app_log().info(
                f"allowedCurationLabels for {identifier}: received "
                + (
                    ", ".join(f"'{lbl}'" for lbl in labels)
                    if labels
                    else "(empty — none configured)"
                )
            )
        except Exception:
            pass
        return labels

    def discover_curation_labels(
        self, persistent_ids: list[str], sample_size: int = 5
    ) -> list[str]:
        """Union of allowed labels across a sample of datasets.

        Allowed labels can vary per collection/dataset, so probe the first
        few datasets until at least one reports a non-empty set. Order of
        first appearance is preserved.
        """
        labels: list[str] = []
        for pid in (persistent_ids or [])[: max(1, sample_size)]:
            try:
                for label in self.get_allowed_curation_labels(pid):
                    if label not in labels:
                        labels.append(label)
            except Exception:
                continue
            if labels:
                break
        if not labels:
            # Fall back to sampling the rest if the head had none configured
            for pid in (persistent_ids or [])[max(1, sample_size) :]:
                try:
                    for label in self.get_allowed_curation_labels(pid):
                        if label not in labels:
                            labels.append(label)
                except Exception:
                    continue
                if labels:
                    break
        return labels

    def fetch_allowed_labels_shared(  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
        self, collection: str, probe_pids: list[str], max_attempts: int = 3
    ) -> list[str]:
        """Return allowed labels via the top-level shared cache (probed once).

        Memory cache first; on miss, probe drafts in order and stop at the
        first non-empty answer, so one discovery round costs a single API
        call. A stamped disk entry (first alias use) serves every later
        session with zero calls; only a new top-level collection (or an
        unstamped legacy entry, once) misses the cache. A 200-confirmed
        empty answer stamps [] exactly once; transport/server errors
        (nothing answered) are cached in memory only and retried next
        session — never frozen to disk. See last_allowed_probe_answered().
        """
        try:
            cached = get_cached_allowed_labels(self._base_url, collection)
        except Exception:
            cached = None
        if cached is not None:
            try:
                get_app_log().info(
                    "allowedCurationLabels: cache hit for "
                    f"'{collection or 'whole repository'}': "
                    + (", ".join(f"'{lbl}'" for lbl in cached) if cached else "(empty)")
                )
            except Exception:
                pass
            return list(cached)
        labels: list[str] = []
        try:
            attempts = max(1, int(max_attempts or 1))
        except Exception:
            attempts = 3
        probed = 0
        answered = False
        for pid in (probe_pids or [])[:attempts]:
            if not pid:
                continue
            probed += 1
            try:
                self._last_allowed_got_200 = False
                found = self.get_allowed_curation_labels(pid)
                if self._last_allowed_got_200:
                    answered = True
            except Exception:
                found = []
            for label in found or []:
                if label not in labels:
                    labels.append(label)
            if labels:
                break
        try:
            self._last_fetch_answered = bool(answered)
        except Exception:
            pass
        try:
            get_app_log().info(
                f"allowedCurationLabels: probed {probed} dataset(s), "
                + (
                    ", ".join(f"'{lbl}'" for lbl in labels)
                    if labels
                    else (
                        "no dataset answered — will retry next session"
                        if not answered
                        else "none configured"
                    )
                )
            )
        except Exception:
            pass
        try:
            set_cached_allowed_labels(self._base_url, collection, labels)
        except Exception:
            pass
        return labels

    def last_allowed_probe_answered(self) -> bool:
        """Whether the latest shared probe round got a server answer.

        True when at least one attempt returned HTTP 200 (labels found or
        confirmed-empty). False after transport/server errors or when no
        round ran — callers must not stamp the disk slot in that case.
        """
        try:
            return bool(getattr(self, "_last_fetch_answered", False))
        except Exception:
            return False

    # -- metadata blocks (field catalog) ------------------------------------

    def get_metadatablock_names(self) -> list[str]:
        """Block names from GET /api/metadatablocks ([] when unavailable)."""
        try:
            payload = self._get_json("/api/metadatablocks")
        except Exception:
            return []
        return parse_metadatablock_names(payload)

    def get_metadatablock_display_names(self) -> dict[str, str]:
        """{block name: display name} from GET /api/metadatablocks ({} on miss)."""
        try:
            payload = self._get_json("/api/metadatablocks")
        except Exception:
            return {}
        return parse_metadatablock_display_names(payload)

    def get_metadatablock_fields(self, block: str) -> list[dict[str, Any]]:
        """[{block, field, label}] for one block ([] when unavailable)."""
        try:
            payload = self._get_json(f"/api/metadatablocks/{block}")
        except Exception:
            return []
        return parse_metadatablock_fields(payload)

    def fetch_metadata_field_catalog(self) -> list[dict[str, Any]]:
        """Full field catalog across blocks (memory/disk cache first).

        One /api/metadatablocks call plus one per block on miss; cached per
        instance, so the Review-configuration page costs zero calls on
        repeat opens. Each field carries block_label (the block's display
        name) alongside block/field/label. Empty results are NOT served
        from memory — [] means the fetch failed, so the next call retries
        instead of freezing an empty catalog in the process. Never raises.
        """
        try:
            cached = get_cached_metadata_fields(self._base_url)
        except Exception:
            cached = None
        if cached:
            return list(cached)
        fields: list[dict[str, str]] = []
        try:
            labels = self.get_metadatablock_display_names()
        except Exception:
            labels = {}
        try:
            names = list(labels) if labels else self.get_metadatablock_names()
            for block in names:
                try:
                    for entry in self.get_metadatablock_fields(block):
                        if isinstance(entry, dict) and entry.get("field"):
                            entry["block_label"] = labels.get(block, "")
                            fields.append(entry)
                except Exception:
                    continue
        except Exception:
            fields = []
        try:
            set_cached_metadata_fields(self._base_url, fields)
        except Exception:
            pass
        return fields

    def list_curation_states(self) -> list[dict[str, Any]] | None:
        """Bulk curation-status report for ALL draft datasets (one CSV call).

        Returns parsed rows on success (possibly empty), or None when the
        caller lacks permission or the network fails — callers fall back to
        per-dataset curationStatus in that case. Other HTTP errors propagate.
        """
        try:
            text = self._get_text("/api/datasets/listCurationStates")
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                get_app_log().info(
                    "listCurationStates unavailable "
                    f"({resp.status_code}) — falling back to per-dataset curationStatus"
                )
                return None
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            return None
        return parse_curation_states_csv(text)

    def compare_versions(
        self,
        identifier: str,
        old: str = ":latest-published",
        new: str = ":draft",
    ) -> dict[str, Any] | None:
        """Diff two dataset versions (default: published vs draft).

        Wraps GET /api/datasets/{id}/versions/{old}/compare/{new}, which
        returns changed metadata/terms fields plus added/removed/replaced
        files. Returns the normalized parse_version_compare() dict, or None
        when there is nothing comparable (no published version yet, draft
        missing, 4xx) or the network fails. Other HTTP errors propagate.
        """
        if ":" in identifier:
            path = f"/api/datasets/:persistentId/versions/{old}/compare/{new}"
            params: dict[str, str] | None = {"persistentId": identifier}
        else:
            path = f"/api/datasets/{identifier}/versions/{old}/compare/{new}"
            params = None
        try:
            payload = self._get_json(path, params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                get_app_log().info(
                    f"compare {old}→{new} unavailable for {identifier} ({resp.status_code})"
                )
                return None
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            return None
        return parse_version_compare(payload)

    def list_versions(self, identifier: str) -> list[dict[str, str]]:
        """All versions of a dataset (oldest-first as returned) for timelines.

        Returns [] when the dataset has no visible versions, on 4xx, or on
        network failure — callers treat this as best-effort timeline data.
        """
        if ":" in identifier:
            path = "/api/datasets/:persistentId/versions"
            params: dict[str, str] | None = {"persistentId": identifier}
        else:
            path = f"/api/datasets/{identifier}/versions"
            params = None
        try:
            payload = self._get_json(path, params=params)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                return []
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            return []
        return parse_dataset_versions((payload or {}).get("data"))

    def get_timestamps(self, identifier: str, numeric_id: Any = None) -> dict[str, str]:
        """Lifecycle timestamps for a dataset (create/publication/DOI/draft touches).

        Wraps GET /api/datasets/{id}/timestamps. Tries the :persistentId form
        first, then the numeric dataset id when known (some instances only
        route one form). Returns {} when unavailable (4xx) or on network
        failure — callers treat this as best-effort timeline data.
        """
        candidates: list[tuple[str, dict[str, str] | None]] = []
        if ":" in identifier:
            candidates.append(
                ("/api/datasets/:persistentId/timestamps", {"persistentId": identifier})
            )
        else:
            candidates.append((f"/api/datasets/{identifier}/timestamps", None))
        try:
            numeric = int(numeric_id)
            candidates.append((f"/api/datasets/{numeric}/timestamps", None))
        except Exception:
            pass
        for path, params in candidates:
            try:
                payload = self._get_json(path, params=params)
            except requests.HTTPError as exc:
                resp = getattr(exc, "response", None)
                if resp is not None and resp.status_code in (400, 401, 403, 404):
                    continue
                raise
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                ConnectionResetError,
            ):
                return {}
            parsed = parse_timestamps(payload)
            if parsed:
                return parsed
        return {}

    def find_review_submissions(
        self,
        persistent_id: str,
        per_page: int = 100,
        max_pages: int = 5,
    ) -> list[dict[str, str]]:
        """Review-submission events for a dataset from the user's notifications.

        Dataverse exposes no submitted-for-review timestamp on the dataset
        itself; submission does notify curators (SUBMITTEDDS), and those
        notifications carry sentTimestamp. Scans the token owner's inbox in
        in-app format (newest first), matching on the structured
        datasetPersistentIdentifier — no text comparison. The collection name
        comes from each note's ownerDisplayName as pulled from the API.
        Returns matches (possibly []) — never raises for 4xx/network issues.
        """
        matches: list[dict[str, str]] = []
        if not (persistent_id or "").strip():
            return matches
        try:
            for page in range(max_pages):
                try:
                    payload = self._get_json(
                        "/api/notifications/all",
                        params={
                            "limit": str(per_page),
                            "offset": str(page * per_page),
                            "inAppNotificationFormat": "true",
                        },
                    )
                except requests.HTTPError as exc:
                    resp = getattr(exc, "response", None)
                    if resp is not None and resp.status_code in (400, 401, 403, 404):
                        break
                    raise
                items = (payload or {}).get("data")
                if isinstance(items, dict):
                    # Real shape: {"notifications": [...], ...}
                    items = items.get("notifications") or []
                if not isinstance(items, list):
                    break
                for note in items:
                    hit = note_review_submission(persistent_id, note)
                    if hit and hit not in matches:
                        matches.append(hit)
                if len(items) < per_page:
                    break
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
        ):
            pass
        return matches

    def set_curation_label(self, identifier: str, label: str) -> bool:
        """Assign a curation label to a draft dataset. Returns True on success."""
        from curation.applog import log_response

        path, base_params = self._curation_paths(identifier, "curationStatus")
        params = dict(base_params or {})
        params["label"] = label
        try:
            start = time.monotonic()
            response = self._session.put(
                self._api(path),
                params=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            log_response("PUT", str(response.url), response.status_code, elapsed_ms, label)
            if not response.ok:
                get_app_log().error(
                    f"PUT {response.url} → {response.status_code}: {response.text[:300]}"
                )
            response.raise_for_status()
            return True
        except Exception as exc:
            get_app_log().error(f"PUT {path} label={label!r} failed: {exc}")
            return False

    def delete_curation_label(self, identifier: str) -> bool:
        """Remove the curation label from a draft dataset. Returns True on success."""
        from curation.applog import log_response

        path, params = self._curation_paths(identifier, "curationStatus")
        try:
            start = time.monotonic()
            response = self._session.delete(
                self._api(path),
                params=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            log_response("DELETE", str(response.url), response.status_code, elapsed_ms, "")
            if not response.ok:
                get_app_log().error(
                    f"DELETE {response.url} → {response.status_code}: {response.text[:300]}"
                )
            response.raise_for_status()
            return True
        except Exception as exc:
            get_app_log().error(f"DELETE {path} failed: {exc}")
            return False

    # -- metadata ------------------------------------------------------------

    def get_dataset_metadata(self, identifier: str) -> dict[str, Any]:
        if ":" in identifier:
            payload = self._get_json(
                "/api/datasets/:persistentId",
                params={"persistentId": identifier},
            )
        else:
            payload = self._get_json(f"/api/datasets/{identifier}")
        data: dict[str, Any] = payload.get("data", {})
        return data

    def get_guestbook(self, guestbook_id: int | str) -> dict[str, Any]:
        """Fetch one guestbook definition (required fields + custom questions).

        Dataverse requires an API token for this call. The returned dict is
        what the download window renders: ``nameRequired``/``emailRequired``/
        ``institutionRequired``/``positionRequired`` plus ``customQuestions``
        (each with ``id``, ``question``, ``required``, ``type`` and, for
        type ``options``, ``optionValues``).
        """
        payload = self._get_json(f"/api/guestbooks/{guestbook_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    def get_current_user(self) -> dict[str, Any]:
        """Best-effort account details for guestbook prefill.

        Never raises: a missing/limited token just means the download window
        starts with empty fields. `affiliation` is the guestbook's
        institution; the account may have no position (the window then asks
        for it, because Dataverse rejects a missing required position).
        """
        try:
            payload = self._get_json("/api/users/:me")
        except Exception:
            return {}
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    def get_file_inventory(self, identifier: str, version: str = "draft") -> list[dict[str, Any]]:
        data, api_version, tried = self._fetch_version_data(identifier, version)
        if api_version != f":{version.lstrip(':').lower()}":
            get_app_log().error(
                f"Inventory for {identifier}: requested :{version} "
                f"unavailable, using {api_version} (tried {tried}) — "
                "verify you are reviewing the intended version"
            )
        return normalize_files(_version_files_data(data))

    def get_variable_metadata(self, file_id: str) -> dict[str, dict[str, str]] | None:
        """Variable-level metadata for one tabular file, from its DDI.

        Returns ``{variable name: {"label": str, "type": str}}`` (label may
        be empty), or None when the fetch/parse fails — callers treat None
        as "unknown coverage", never as "no documentation".
        """
        try:
            text = self._get_text(f"/api/access/datafile/{file_id}/metadata/ddi")
            import xml.etree.ElementTree as ET

            root = ET.fromstring(text)
        except Exception:
            return None
        out: dict[str, dict[str, str]] = {}
        try:
            for var in root.iter():
                tag = var.tag.rsplit("}", 1)[-1]
                if tag != "var":
                    continue
                name = str(var.get("name") or "").strip()
                if not name:
                    continue
                label = ""
                intrvl = str(var.get("intrvl") or "")
                for child in var:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "labl":
                        label = (child.text or "").strip()
                out[name] = {"label": label, "type": intrvl}
        except Exception:
            return None
        return out or None
