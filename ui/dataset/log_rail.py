"""The dataset log card: the curator's own action trail for this dataset."""

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QSizePolicy,
)

from ui.dataset.state import DetailState

if TYPE_CHECKING:
    from curation.storage import AppState
from ui.i18n import t
from ui.widgets import (
    add_info_tip,
    make_card,
    make_list,
)


def format_log_timestamp(raw: str) -> str:
    """Date + time when a time is present; date-only values stay date-only."""
    s = (raw or "").strip()
    if not s:
        return t("common.em_dash")
    normalized = s.replace("T", " ").replace("Z", "").strip()
    # Drop seconds + fractional/timezone suffixes, keep HH:MM.
    parts = normalized.split()
    if len(parts) >= 2 and len(parts[0]) == 10 and parts[1][:2].isdigit():
        return f"{parts[0]} {parts[1][:5]}"
    if len(s) > 10 and s[10] in ("T", " "):
        return s[:16].replace("T", " ")
    return s[:10]


def parse_log_timestamp(raw: str) -> float:
    """Parse a timestamp to epoch milliseconds for sorting.

    Handles ISO 8601 (T or space separator, Z or offset), date-only and
    common display formats. Returns 0 on failure or when absent.
    """
    s = (raw or "").strip()
    if not s:
        return 0.0
    try:
        from datetime import UTC, datetime

        normalized = s.replace("Z", "+00:00")
        if "T" not in normalized and " " in normalized and len(normalized) > 10:
            normalized = normalized.replace(" ", "T", 1)
        if "." in normalized:
            base, frac = normalized.split(".", 1)
            normalized = base + "." + (frac + "000000")[:6]
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp() * 1000.0
    except Exception:
        return 0.0


class _LogEvents:
    """Collect (sort_key, display text) pairs for the timeline."""

    def __init__(self) -> None:
        self.items: list[tuple[float, str]] = []
        self.dated_creations: list[str] = []
        self.published_days: set[str] = set()

    def _line(self, stamp: str, text: str) -> str:
        return t("detail.dataset_log.timeline_format", stamp=format_log_timestamp(stamp), text=text)

    def add(self, ts: Any, text: str) -> None:
        raw = str(ts or "").strip()
        if raw:
            self.items.append((parse_log_timestamp(raw), self._line(raw, text)))
        else:
            self.items.append((0.0, t("common.em_dash") + " " + text))

    def dated(self, ts: str, text: str) -> None:
        """Add a line that is always timestamped (never a dash placeholder)."""
        if ts:
            self.items.append((parse_log_timestamp(ts), self._line(ts, text)))


class LogRail(DetailState):
    """The dataset log card: the curator's own action trail for this dataset."""

    def _build_dataset_log_card(self) -> QFrame:
        card, body, _title, _header = make_card(t("detail.sections.dataset_log"))
        add_info_tip(
            _header,
            t("detail.dataset_log.tip"),
            name=t("detail.sections.dataset_log"),
            group="Queue",
        )
        self._dataset_log = make_list(flush=True)
        # Tall timeline: minimum keeps it readable on short screens, the
        # higher maximum + Expanding policy lets it claim the sidebar's
        # free space (the card carries stretch 1 in the sidebar layout).
        self._dataset_log.setMinimumHeight(320)
        self._dataset_log.setMaximumHeight(650)
        self._dataset_log.setSizeAdjustPolicy(
            QAbstractItemView.SizeAdjustPolicy.AdjustToContentsOnFirstShow
        )
        self._dataset_log.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._dataset_log.setWordWrap(True)
        self._dataset_log.setToolTip(t("detail.dataset_log.tip"))
        # Edge to edge (dv-gfx.17): the list is the card's content, not a
        # box inside a box, so the card's own padding would inset it twice.
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._dataset_log)
        return card

    def _state(self) -> "AppState | None":
        """Open the workspace state.db (best-effort; returns None on failure)."""
        try:
            from curation.storage import open_state

            return open_state(self._config.app.workspace)
        except Exception:
            return None

    def _log_action(
        self, action: str, notes: str = "", details: dict[str, Any] | None = None
    ) -> None:
        st = None
        try:
            st = self._state()
            if st is None:
                return
            st.log_action(self._pid, action, notes=notes, details=details or {})
        except Exception:
            pass
        finally:
            if st is not None:
                try:
                    st.close()
                except Exception:
                    pass
        try:
            self._refresh_dataset_log()
        except Exception:
            pass

    def _version_events(self, events: _LogEvents) -> None:
        """Version lifecycle: draft created, published, deaccessioned."""
        versions = self._versions if isinstance(self._versions, list) else []
        for v in versions:
            if not isinstance(v, dict):
                continue
            num = v.get("number", "") or ""
            state = (v.get("state", "") or "").upper()
            ct, rt = v.get("create_time", ""), v.get("release_time", "")
            if ct:
                events.dated_creations.append(ct)
            if state == "DRAFT":
                events.add(ct, t("detail.dataset_log.version_draft_created", num=num))
            elif state == "DEACCESSIONED":
                events.add(rt or ct, t("detail.dataset_log.version_deaccessioned", num=num))
            else:
                if rt:
                    events.add(rt, t("detail.dataset_log.version_published", num=num))
                    events.published_days.add(rt[:10])
                if ct and ct[:10] != (rt or "")[:10]:
                    events.add(ct, t("detail.dataset_log.version_created", num=num))
        if events.dated_creations:
            events.dated(
                sorted(events.dated_creations)[0], t("detail.dataset_log.first_created")
            )

    def _timestamp_events(self, events: _LogEvents) -> None:
        """Dataset-level record dates from the timestamps endpoint."""
        ts = self._timestamps if isinstance(self._timestamps, dict) else {}
        created = str(ts.get("createTime") or "")
        if not events.dated_creations and created:
            # No version dates at all — timestamps are the only source.
            events.dated(created, t("detail.dataset_log.first_created"))
        published = str(ts.get("publicationTime") or "")
        if (
            published
            and published[:10] != created[:10]
            and published[:10] not in events.published_days
        ):
            # Only shown when it differs from creation (per curator request)
            # and no version event already covers that day.
            events.dated(published, t("detail.dataset_log.first_published"))
        doi = str(ts.get("globalIdCreateTime") or "")
        if doi:
            events.dated(doi, t("detail.dataset_log.doi_minted"))
        touched = str(ts.get("lastUpdateTime") or "")
        if touched:
            events.dated(touched, t("detail.dataset_log.draft_updated"))

    def _submission_events(self, events: _LogEvents) -> None:
        """Review submissions (SUBMITTEDDS inbox notes, PID-matched)."""
        for sub in self._review_submissions if isinstance(self._review_submissions, list) else []:
            if not isinstance(sub, dict):
                continue
            when = str(sub.get("time") or "")
            dv = str(sub.get("dataverse") or "").strip()
            who = str(sub.get("requestor") or "").strip()
            text = t("detail.dataset_log.submitted_for_review")
            if dv:
                text += t("detail.dataset_log.publish_in", dataset=dv)
            if who:
                text += t("detail.dataset_log.by", who=who)
            events.add(when, text)

    def _curation_events(self, events: _LogEvents) -> None:
        for h in (self._curation or {}).get("history") or []:
            if not isinstance(h, dict):
                continue
            label = str(h.get("label") or "").strip()
            if not label:
                continue
            who = str(h.get("assigner") or "").strip()
            text = t("detail.dataset_log.curation_label_assigned", label=label)
            if who:
                text += t("detail.dataset_log.by", who=who)
            events.add(h.get("time", ""), text)

    def _local_action_events(self, events: _LogEvents) -> None:
        st = None
        try:
            st = self._state()
            actions = st.list_actions(self._pid, limit=50) if st is not None else []
        except Exception:
            actions = []
        finally:
            if st is not None:
                try:
                    st.close()
                except Exception:
                    pass
        local_text = {
            "downloaded": t("detail.dataset_log.action_downloaded"),
            "checks_run": t("detail.dataset_log.action_checks_run"),
            "decision": t("detail.dataset_log.action_decision"),
            "exported": t("detail.dataset_log.action_exported"),
            "response_exported": t("detail.dataset_log.action_response_exported"),
            "disposition": t("detail.dataset_log.action_disposition"),
            "curation_record_exported": t("detail.dataset_log.action_record"),
            "sensitivity_reviewed": t("detail.dataset_log.action_sensitivity"),
            "dictionary_drafted": t("detail.dataset_log.action_dictionary"),
            "follow_up_opened": t("detail.dataset_log.action_follow_up_opened"),
            "follow_up_closed": t("detail.dataset_log.action_follow_up_closed"),
        }
        for a in actions:
            act = a.get("action") or ""
            if act not in local_text:
                continue
            notes = (a.get("notes") or "").strip()
            text = local_text[act] + (
                t("detail.dataset_log.action_notes", notes=notes[:90]) if notes else ""
            )
            events.add(a.get("timestamp", ""), text)

    def _inventory_events(self, events: _LogEvents) -> None:
        """Embargo / retention dates from the file inventory."""
        for entry in self._inventory if isinstance(self._inventory, list) else []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip() or t("detail.dataset_log.unnamed_file")
            embargo = str(entry.get("embargo_date") or "").strip()
            if embargo:
                events.add(
                    embargo,
                    t("detail.dataset_log.embargoed", path=path, date=embargo[:10]),
                )
            retention = str(entry.get("retention") or "").strip()
            if retention:
                events.add(
                    retention,
                    t("detail.dataset_log.retention", path=path, value=retention[:60]),
                )

    def _paint_log(self, events: _LogEvents) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        try:
            self._dataset_log.clear()
            if not events.items:
                self._dataset_log.addItem(t("detail.dataset_log.no_history"))
                return
            events.items.sort(key=lambda e: e[0], reverse=True)  # epoch_ms
            for _key, text in events.items[:100]:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                self._dataset_log.addItem(item)
        except Exception:
            pass

    def _refresh_dataset_log(self) -> None:
        """Newest-first timeline: versions, record dates, review, labels, files, local actions.

        Sources (each best-effort; missing sources are simply skipped):
        - versions list: draft created / version published / deaccessioned
        - timestamps endpoint: first published (when different from created),
          DOI minted, draft last updated
        - notifications inbox: submitted for review (matched by title)
        - curation history: label assigned (+ assigner)
        - file inventory: embargo / retention dates
        - local state.db: downloaded / checks run / decision / exported
        """
        events = _LogEvents()
        self._version_events(events)
        self._timestamp_events(events)
        self._submission_events(events)
        self._curation_events(events)
        self._local_action_events(events)
        self._inventory_events(events)
        self._paint_log(events)
