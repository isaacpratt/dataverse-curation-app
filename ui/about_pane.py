"""About pane: non-modal stack page describing the app (replaces the popup)."""

from typing import Any, ClassVar

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import t
from ui.theme import (
    ACTIVE_THEME,
    TEXT_SUBTLE,
    transparent_surface_qss,
)
from ui.widgets import (
    AppButton,
    make_action_button,
    make_body_label,
    make_page_heading,
    make_progress_bar,
    set_sheet,
)


def _app_version() -> str:
    try:
        from engine import __version__

        return str(__version__)
    except Exception:
        return "0.1.0"


def _platform_text() -> str:
    """OS version without ``platform.platform()``'s ``cmd /c ver`` subprocess.

    ``platform.platform()`` shells out twice on Windows (~110 ms), which used
    to sit on the startup path; ``sys.getwindowsversion()`` answers locally.
    """
    import sys as _sys

    try:
        if _sys.platform == "win32":
            v = _sys.getwindowsversion()
            return t("about.diag.windows", major=v.major, minor=v.minor, build=v.build)
        import platform as _platform

        return f"{_platform.system()} {_platform.release()}"
    except Exception:
        return t("common.unknown")


def _build_provenance() -> tuple[str, str]:
    """(git sha, uv.lock hash) for a support request; 'dev'/'unknown' in dev."""
    import hashlib as _hashlib
    import json as _json
    import subprocess as _subprocess
    import sys as _sys
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parent.parent
    if getattr(_sys, "frozen", False):
        for candidate in (
            _Path(_sys.executable).parent / "build_info.json",
            _Path(_sys.executable).parent.parent / "build_info.json",
        ):
            try:
                info = _json.loads(candidate.read_text(encoding="utf-8"))
                return str(info.get("git_sha", "unknown")), str(info.get("lock_hash", "unknown"))
            except Exception:
                continue
        return "unknown", "unknown"
    sha = "dev"
    try:
        out = _subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            stderr=_subprocess.DEVNULL,
        )
        sha = out.decode().strip() or "dev"
    except Exception:
        pass
    lock_hash = "unknown"
    try:
        lock_hash = _hashlib.sha256((repo_root / "uv.lock").read_bytes()).hexdigest()[:12]
    except Exception:
        pass
    return sha, lock_hash


def _diag_text() -> str:
    """Environment facts for a support request — never the API token."""
    import sys as _sys

    try:
        from PySide6 import __version__ as _qt_version
    except Exception:
        _qt_version = "unknown"
    install = t("about.diag.frozen") if getattr(_sys, "frozen", False) else t("about.diag.source")
    lines = [
        t("about.diag.version", value=_app_version()),
        t("about.diag.python", value=_sys.version.split()[0]),
        t("about.diag.qt", value=_qt_version),
        t("about.diag.platform", value=_platform_text()),
        t("about.diag.install", value=install),
    ]
    sha, lock_hash = _build_provenance()
    lines.append(t("about.diag.commit", value=sha))
    lines.append(t("about.diag.lock_hash", value=lock_hash))
    try:
        from curation.config import Config

        cfg = Config.load(None)
        lines.append(t("about.diag.workspace", value=cfg.app.workspace))
        lines.append(t("about.diag.base_url", value=cfg.dataverse.base_url))
        token = (cfg.dataverse.api_token or "").strip()
        lines.append(
            t(
                "about.diag.api_token",
                value=t("about.diag.set") if token else t("about.diag.not_set"),
            )
        )
    except Exception:
        lines.append(t("about.diag.config_unavailable"))
    return "\n".join(lines)


class AboutPane(QWidget):
    """Short product overview with a Back button. Emits `discarded` on Back."""

    discarded = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Scoped to self: a bare `background` rule would act subtree-wide
        # and override app-level backgrounds below this pane.
        self.setObjectName("AboutPane")
        set_sheet(self, "page_background", ("AboutPane",))

        # Updates section state (the feed logic lives in ui/updater.py).
        self._update_state = (
            "idle"  # idle|checking|unavailable|up_to_date|available|downloading|ready|failed
        )
        self._update_version: str | None = None
        self._update_pending_info = None  # velopack UpdateInfo after a successful download
        self._check_worker: Any = None
        self._download_worker: Any = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        # Shared page-heading contract (HeadlineLG theme token)
        # same title look as Settings, Review configuration and Log.
        heading, _subtitle = make_page_heading(t("about.heading"))
        outer.addWidget(heading)

        card = QFrame()
        card.setObjectName("Card")
        set_sheet(card, "surface_frame", "SURFACE_CARD", "BORDER_SUBTLE", selector="QFrame#Card")
        body = QVBoxLayout(card)
        body.setContentsMargins(20, 20, 20, 20)
        body.setSpacing(10)

        title = QLabel(
            t(
                "about.title",
                version=_app_version(),
                muted=TEXT_SUBTLE,
            )
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        # The product title wears the theme's HeadlineMD token (16px
        # semibold) - the app's card-title look, with no inline style.
        title.setObjectName("HeadlineMD")
        title.setWordWrap(True)
        # App mark beside the title (2026-10-06 Dataverse Docent rebrand;
        # 2026-10-07 bumped to the icon's native 64×64).
        head_row = QHBoxLayout()
        head_row.setSpacing(12)
        head_row.setContentsMargins(0, 0, 0, 0)
        mark = QLabel()
        mark.setObjectName("DocentMark")
        try:
            from ui.theme import app_icon_path

            pix = QPixmap(app_icon_path(ACTIVE_THEME))
            if not pix.isNull():
                mark.setPixmap(pix.scaledToHeight(64, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            pass
        mark.setStyleSheet(transparent_surface_qss("DocentMark", theme=ACTIVE_THEME))
        mark.setFixedWidth(64)
        head_row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        head_row.addWidget(title, 1)
        body.addLayout(head_row)

        # Two columns (2026-10-02 minor): overview left, environment
        # facts + copy right — support details where they can be found.
        cols = QHBoxLayout()
        cols.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(10)
        blurb = make_body_label(t("about.blurb"))
        left.addWidget(blurb)
        bullets = make_body_label(t("about.bullets"))
        bullets.setTextFormat(Qt.TextFormat.RichText)
        left.addWidget(bullets)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        diag_head = QLabel(t("about.diagnostics"))
        diag_head.setObjectName("LabelMD")
        right.addWidget(diag_head)
        diag = QLabel(_diag_text())
        diag.setTextFormat(Qt.TextFormat.PlainText)
        diag.setWordWrap(True)
        diag.setObjectName("MonoSM")
        right.addWidget(diag)
        copy_btn = make_action_button(t("about.copy"), kind="secondary")
        copy_btn.setToolTip(t("about.copy_tip"))
        copy_btn.clicked.connect(lambda: self._copy_diagnostics(copy_btn))
        right.addWidget(copy_btn)
        right.addStretch(1)
        cols.addLayout(right, 2)

        body.addLayout(cols)

        updates = self._build_updates_section()
        body.addWidget(updates)

        try:
            from ui.theme import selectable_labels

            selectable_labels(card)
        except Exception:
            pass
        outer.addWidget(card)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(8)
        back_btn = make_action_button(t("about.close"), kind="secondary")
        back_btn.setAccessibleName(t("about.close_a11y"))
        back_btn.clicked.connect(lambda: self.discarded.emit())
        try:
            from ui.icons import role_icon as _about_icon

            back_btn.setIcon(_about_icon("back"))
        except Exception:
            pass
        row.addWidget(back_btn)
        row.addStretch(1)
        outer.addLayout(row)

    def _build_updates_section(self) -> QFrame:
        """Build the Updates block: status, last check, one action button, a bar."""
        import ui.updater as _updater

        card = QFrame()
        card.setObjectName("UpdatesCard")
        card.setStyleSheet(transparent_surface_qss("UpdatesCard", theme=ACTIVE_THEME))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(6)

        divider = QFrame()
        divider.setObjectName("UpdatesDivider")
        divider.setFixedHeight(1)
        # theme-allow: hairline divider tinted with the shared border role,
        # nothing the kit owns (no card/badge/label mixin matches a bare rule)
        set_sheet(divider, "rule", "QFrame", "BORDER_SUBTLE")
        layout.addWidget(divider)

        head = QLabel(t("about.updates.title"))
        head.setObjectName("LabelMD")
        layout.addWidget(head)

        self._update_status = make_body_label("")
        self._update_status.setObjectName("BodySM")
        layout.addWidget(self._update_status)

        self._update_last_checked = make_body_label("")
        self._update_last_checked.setObjectName("CaptionSM")
        layout.addWidget(self._update_last_checked)

        self._update_progress = make_progress_bar(height=6)
        self._update_progress.setVisible(False)
        self._update_progress.setRange(0, 100)
        layout.addWidget(self._update_progress)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        self._update_button = make_action_button(t("about.updates.check_now"), kind="primary")
        self._update_button.clicked.connect(self._on_update_button)
        row.addWidget(self._update_button)
        row.addStretch(1)
        layout.addLayout(row)

        try:
            _updater.bus().stateChanged.connect(self._refresh_update_ui)
        except Exception:
            pass
        self._refresh_update_ui()
        return card

    def _copy_diagnostics(self, btn: AppButton) -> None:
        """Copy the diagnostics block to the clipboard, with brief feedback."""
        try:
            QApplication.clipboard().setText(_diag_text())
            btn.setText(t("about.copied"))

            def _restore() -> None:
                try:
                    btn.setText(t("about.copy"))
                except Exception:
                    pass

            QTimer.singleShot(1600, _restore)
        except Exception:
            pass

    # -- Updates section -----------------------------------------------

    _REASON_KEYS: ClassVar[dict[str, str]] = {
        "network": "about.updates.reason_network",
        "timeout": "about.updates.reason_timeout",
        "rate_limited": "about.updates.reason_rate_limited",
        "feed": "about.updates.reason_feed",
        "unknown": "about.updates.reason_unknown",
    }

    def _reason_text(self, reason: str | None) -> str:
        key = self._REASON_KEYS.get(reason or "unknown", self._REASON_KEYS["unknown"])
        try:
            return t(key)
        except Exception:
            return t("about.updates.reason_unknown")

    def _format_checked(self) -> str:
        import time as _time

        import ui.updater as _updater

        stamp = _updater.last_checked_at()
        if stamp is None:
            return t("about.updates.never_checked")
        shown = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(stamp))
        return t("about.updates.last_checked", when=shown)

    def _set_update_controls(
        self,
        *,
        status: str,
        button: str | None,
        button_enabled: bool = True,
        show_progress: bool = False,
        progress: int | None = None,
    ) -> None:
        self._update_status.setText(status)
        self._update_last_checked.setText(self._format_checked())
        if progress is not None:
            self._update_progress.setValue(progress)
        self._update_progress.setVisible(show_progress)
        if button is None:
            self._update_button.setVisible(False)
        else:
            self._update_button.setVisible(True)
            self._update_button.setText(button)
            self._update_button.setEnabled(button_enabled)

    def _refresh_update_ui(self) -> None:
        import ui.updater as _updater

        if self._update_state == "downloading":
            return  # the download owns the bar until it finishes
        pending = _updater.pending_version()
        if pending or self._update_state == "ready":
            version = pending or self._update_version or ""
            self._update_state = "ready"
            self._update_version = version
            self._set_update_controls(
                status=t("about.updates.ready", version=version),
                button=t("about.updates.restart_now", version=version),
            )
            return
        if self._update_state == "unavailable":
            self._set_update_controls(status=t("about.updates.unavailable"), button=None)
            return
        if self._update_state == "failed":
            # The status line already shows details; only refresh the clock.
            self._update_last_checked.setText(self._format_checked())
            return
        if self._update_state in ("available", "checking"):
            return
        if self._update_state == "idle":
            status = t("about.updates.up_to_date")
            if _updater.last_checked_at() is None:
                status = t("about.updates.never_checked")
            self._set_update_controls(
                status=status,
                button=t("about.updates.check_now"),
            )

    def _on_update_button(self) -> None:
        state = self._update_state
        if state == "available":
            self._start_download()
            return
        if state == "ready":
            self._restart_and_install()
            return
        self._start_check(force=True)

    def _start_check(self, *, force: bool) -> None:
        import ui.updater as _updater

        if self._check_worker is not None and self._check_worker.isRunning():
            return
        self._update_state = "checking"
        self._set_update_controls(
            status=t("about.updates.checking"),
            button=t("about.updates.checking"),
            button_enabled=False,
        )
        worker = _updater.UpdateCheckWorker(force=force)
        worker.finished.connect(self._on_check_finished)
        self._check_worker = worker
        worker.start()

    def _on_check_finished(self, outcome: dict[str, Any]) -> None:
        import ui.updater as _updater

        status = outcome.get("status")
        version = outcome.get("version")
        try:
            if status == "update_available":
                self._update_state = "available"
                self._update_version = version
                self._set_update_controls(
                    status=t("about.updates.available", version=version),
                    button=t("about.updates.download", version=version),
                )
            elif status == "unavailable":
                self._update_state = "unavailable"
                self._set_update_controls(status=t("about.updates.unavailable"), button=None)
            elif status == "failed":
                self._update_state = "failed"
                self._set_update_controls(
                    status=t(
                        "about.updates.failed", reason=self._reason_text(outcome.get("reason"))
                    ),
                    button=t("about.updates.check_now"),
                )
            else:  # up_to_date | cached
                self._update_state = "up_to_date"
                self._set_update_controls(
                    status=t("about.updates.up_to_date"),
                    button=t("about.updates.check_now"),
                )
        finally:
            _updater.notify_state_changed()

    def _start_download(self) -> None:
        import ui.updater as _updater

        self._update_state = "downloading"
        version = self._update_version or ""
        self._set_update_controls(
            status=t("about.updates.downloading", version=version, percent="0"),
            button=None,
            show_progress=True,
            progress=0,
        )
        worker = _updater.UpdateDownloadWorker(info=None)
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(self._on_download_finished)
        self._download_worker = worker
        worker.start()

    def _on_download_progress(self, percent: int) -> None:
        version = self._update_version or ""
        self._update_progress.setValue(percent)
        self._update_status.setText(
            t("about.updates.downloading", version=version, percent=percent)
        )

    def _on_download_finished(self, ok: bool) -> None:
        import ui.updater as _updater

        version = self._update_version or ""
        self._update_pending_info = self._download_worker.info if self._download_worker else None
        if ok:
            self._update_state = "ready"
            self._update_progress.setVisible(False)
            self._set_update_controls(
                status=t("about.updates.ready", version=version),
                button=t("about.updates.restart_now", version=version),
            )
        else:
            self._update_state = "failed"
            self._update_progress.setVisible(False)
            self._set_update_controls(
                status=t("about.updates.check_failed_download"),
                button=t("about.updates.check_now"),
            )
        _updater.notify_state_changed()

    def _restart_and_install(self) -> None:
        from PySide6.QtWidgets import QApplication

        import ui.updater as _updater

        manager = _updater.make_update_manager()
        if manager is not None:
            _updater.apply_update_on_restart(manager, self._update_pending_info)
        app = QApplication.instance()
        if app is not None:
            app.quit()
