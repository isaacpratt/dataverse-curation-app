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

    def _refresh_dataset_log(self) -> None:  # noqa: C901 - grandfathered; complexity burns down as dv-hcg decomposition lands
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
        from PySide6.QtWidgets import QListWidgetItem

        events: list[tuple[str, str]] = []  # (sort_key, display text)

        def _fmt_ts(raw: str) -> str:
            """Display timestamp as date + time when a time is present.

            ISO datetimes (2026-09-15T14:30:00Z, with TZ/seconds, or space-
            separated) render as 'YYYY-MM-DD HH:MM'; date-only values stay
            date-only so embargo/retention dates don't gain a bogus midnight.
            """
            s = (raw or "").strip()
            if not s:
                return t("common.em_dash")
            normalized = s.replace("T", " ").replace("Z", "").strip()
            # Drop seconds + fractional/timezone suffixes, keep HH:MM.
            parts = normalized.split()
            if len(parts) >= 2 and len(parts[0]) == 10 and parts[1][:2].isdigit():
                return f"{parts[0]} {parts[1][:5]}"
            if len(s) > 10 and (s[10] in ("T", " ")):
                return s[:16].replace("T", " ")
            return s[:10]

        def _add(ts: Any, text: str) -> None:
            raw = str(ts or "").strip()
            if raw:
                events.append(
                    (
                        raw,
                        t("detail.dataset_log.timeline_format", stamp=_fmt_ts(raw), text=text),
                    )
                )
            else:
                events.append(("0000", t("common.em_dash") + " " + text))

        versions = self._versions if isinstance(self._versions, list) else []
        dated_creations: list[str] = []
        version_published_days: set[str] = set()
        for v in versions:
            if not isinstance(v, dict):
                continue
            num = v.get("number", "") or ""
            state = (v.get("state", "") or "").upper()
            ct, rt = v.get("create_time", ""), v.get("release_time", "")
            if ct:
                dated_creations.append(ct)
            if state == "DRAFT":
                _add(ct, t("detail.dataset_log.version_draft_created", num=num))
            elif state == "DEACCESSIONED":
                _add(rt or ct, t("detail.dataset_log.version_deaccessioned", num=num))
            else:
                if rt:
                    _add(rt, t("detail.dataset_log.version_published", num=num))
                    version_published_days.add(rt[:10])
                if ct and ct[:10] != (rt or "")[:10]:
                    _add(ct, t("detail.dataset_log.version_created", num=num))
        if dated_creations:
            first = sorted(dated_creations)[0]
            events.append(
                (
                    first,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(first),
                        text=t("detail.dataset_log.first_created"),
                    ),
                )
            )

        # Lifecycle timestamps endpoint (dataset-level record dates).
        ts = self._timestamps if isinstance(self._timestamps, dict) else {}
        ts_created = str(ts.get("createTime") or "")
        if not dated_creations and ts_created:
            # No version dates at all — timestamps are the only source.
            events.append(
                (
                    ts_created,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_created),
                        text=t("detail.dataset_log.first_created"),
                    ),
                )
            )
        ts_published = str(ts.get("publicationTime") or "")
        if (
            ts_published
            and ts_published[:10] != ts_created[:10]
            and ts_published[:10] not in version_published_days
        ):
            # Only shown when it differs from creation (per curator request)
            # and no version event already covers that day.
            events.append(
                (
                    ts_published,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_published),
                        text=t("detail.dataset_log.first_published"),
                    ),
                )
            )
        ts_doi = str(ts.get("globalIdCreateTime") or "")
        if ts_doi:
            events.append(
                (
                    ts_doi,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_doi),
                        text=t("detail.dataset_log.doi_minted"),
                    ),
                )
            )
        ts_touched = str(ts.get("lastUpdateTime") or "")
        if ts_touched:
            events.append(
                (
                    ts_touched,
                    t(
                        "detail.dataset_log.timeline_format",
                        stamp=_fmt_ts(ts_touched),
                        text=t("detail.dataset_log.draft_updated"),
                    ),
                )
            )

        # Review submissions (SUBMITTEDDS inbox notes, PID-matched).
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
            if when:
                events.append(
                    (
                        when,
                        t(
                            "detail.dataset_log.timeline_format",
                            stamp=_fmt_ts(when),
                            text=text,
                        ),
                    )
                )
            else:
                events.append(("0000", t("common.em_dash") + " " + text))

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
            _add(h.get("time", ""), text)

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
        _local_text = {
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
            if act not in _local_text:
                continue
            notes = (a.get("notes") or "").strip()
            text = _local_text[act] + (
                t("detail.dataset_log.action_notes", notes=notes[:90]) if notes else ""
            )
            _add(a.get("timestamp", ""), text)

        # Embargo / retention dates from the file inventory (as applicable).
        for entry in self._inventory if isinstance(self._inventory, list) else []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip() or t("detail.dataset_log.unnamed_file")
            embargo = str(entry.get("embargo_date") or "").strip()
            if embargo:
                _add(
                    embargo,
                    t(
                        "detail.dataset_log.embargoed",
                        path=path,
                        date=embargo[:10],
                    ),
                )
            retention = str(entry.get("retention") or "").strip()
            if retention:
                _add(
                    retention,
                    t(
                        "detail.dataset_log.retention",
                        path=path,
                        value=retention[:60],
                    ),
                )

        try:
            self._dataset_log.clear()
            if not events:
                self._dataset_log.addItem(t("detail.dataset_log.no_history"))
                return
            events.sort(key=lambda e: e[0], reverse=True)
            for _key, text in events[:100]:
                item = QListWidgetItem(text)
                item.setToolTip(text)
                self._dataset_log.addItem(item)
        except Exception:
            pass
