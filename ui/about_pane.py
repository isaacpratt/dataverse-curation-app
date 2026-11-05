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
    BACKGROUND,
    ON_SECONDARY_CONTAINER,
    ON_SURFACE,
    ON_SURFACE_VARIANT,
    OUTLINE_VARIANT,
    SURFACE_CONTAINER_LOWEST,
)
from ui.widgets import AppButton


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
    try:
        from config import Config

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
        self.setStyleSheet(f"QWidget#AboutPane {{ background: {BACKGROUND}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QLabel(t("about.heading"))
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: 600; color: {ON_SURFACE}; "
            "border: none; background: transparent;"
        )
        outer.addWidget(heading)

        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            f"QFrame#Card {{ background: {SURFACE_CONTAINER_LOWEST}; border: 1px solid {OUTLINE_VARIANT}; border-radius: 8px; }}"
        )
        body = QVBoxLayout(card)
        body.setContentsMargins(20, 20, 20, 20)
        body.setSpacing(10)

        title = QLabel(
            t(
                "about.title",
                version=_app_version(),
                muted=ON_SECONDARY_CONTAINER,
            )
        )
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {ON_SURFACE}; "
            "border: none; background: transparent;"
        )
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
        mark.setStyleSheet("border: none; background: transparent;")
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
        blurb = QLabel(t("about.blurb"))
        blurb.setWordWrap(True)
        blurb.setStyleSheet(
            f"font-size: 13px; color: {ON_SURFACE_VARIANT}; border: none; background: transparent;"
        )
        left.addWidget(blurb)

        bullets = QLabel(t("about.bullets"))
        bullets.setTextFormat(Qt.RichText)
        bullets.setWordWrap(True)
        bullets.setStyleSheet(
            f"font-size: 13px; color: {ON_SURFACE_VARIANT}; border: none; background: transparent;"
        )
        left.addWidget(bullets)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        diag_head = QLabel(t("about.diagnostics"))
        diag_head.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {ON_SURFACE_VARIANT}; "
            "letter-spacing: 0.5px; border: none; background: transparent;"
        )
        right.addWidget(diag_head)
        diag = QLabel(_diag_text())
        diag.setTextFormat(Qt.PlainText)
        diag.setWordWrap(True)
        diag.setStyleSheet(
            f"font-size: 12px; color: {ON_SURFACE_VARIANT}; border: none; "
            "background: transparent; font-family: 'JetBrains Mono', Consolas, monospace;"
        )
        right.addWidget(diag)
        copy_btn = AppButton(t("about.copy"), kind="secondary")
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
        back_btn = AppButton(t("about.close"), kind="secondary")
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
