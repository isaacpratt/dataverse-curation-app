"""About pane: non-modal stack page describing the app (replaces the popup)."""

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
    BORDER_SUBTLE,
    SURFACE_CARD,
    TEXT_SUBTLE,
    page_background_qss,
    surface_frame_qss,
    transparent_surface_qss,
)
from ui.widgets import (
    AppButton,
    make_action_button,
    make_body_label,
    make_page_heading,
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Scoped to self: a bare `background` rule would act subtree-wide
        # and override app-level backgrounds below this pane.
        self.setObjectName("AboutPane")
        self.setStyleSheet(page_background_qss("AboutPane"))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        # Shared page-heading contract (HeadlineLG theme token)
        # same title look as Settings, Review configuration and Log.
        heading, _subtitle = make_page_heading(t("about.heading"))
        outer.addWidget(heading)

        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(surface_frame_qss(SURFACE_CARD, BORDER_SUBTLE, selector="QFrame#Card"))
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
        title.setTextFormat(Qt.RichText)
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

            pix = QPixmap(app_icon_path())
            if not pix.isNull():
                mark.setPixmap(pix.scaledToHeight(64, Qt.SmoothTransformation))
        except Exception:
            pass
        mark.setStyleSheet(transparent_surface_qss("DocentMark"))
        mark.setFixedWidth(64)
        head_row.addWidget(mark, 0, Qt.AlignTop)
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
        bullets.setTextFormat(Qt.RichText)
        left.addWidget(bullets)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        diag_head = QLabel(t("about.diagnostics"))
        diag_head.setObjectName("LabelMD")
        right.addWidget(diag_head)
        diag = QLabel(_diag_text())
        diag.setTextFormat(Qt.PlainText)
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
            from ui.icons import icon as _about_icon

            back_btn.setIcon(_about_icon("x"))
        except Exception:
            pass
        row.addWidget(back_btn)
        row.addStretch(1)
        outer.addLayout(row)

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
