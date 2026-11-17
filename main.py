"""Launch the Dataverse Docent entry point.

Default is the desktop GUI; --headless runs the engine on a staged
dataset directory and writes a JSON report (see docs/html/development.html).
"""

import argparse
import sys
from pathlib import Path

from startup_probe import mark
from ui.i18n import t

mark("main.py imported")


# Ensure PyInstaller bundles the GUI even though it is imported lazily
# inside main() (so --headless can run without a display).
# These imports are TYPE_CHECKING-only at runtime to keep --headless fast
# (~300ms + ~100MB saved by not loading Qt). PyInstaller still discovers
# them via the hidden-imports in tools/build_app.py.
from typing import TYPE_CHECKING as _TYPE_CHECKING  # noqa: E402

if _TYPE_CHECKING:  # pragma: no cover  # noqa: E402
    import PySide6  # noqa: F401
    import PySide6.QtCore  # noqa: F401
    import PySide6.QtGui  # noqa: F401
    import PySide6.QtWidgets  # noqa: F401

    import response_draft  # noqa: F401
    import review_rules  # noqa: F401
    import ui.dashboard  # noqa: F401
    import ui.dataset_detail  # noqa: F401
    import ui.main_window  # noqa: F401
    import ui.review_config  # noqa: F401
    import ui.settings_dialog  # noqa: F401
    import ui.workers  # noqa: F401


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=t("app.cli.description"))
    parser.add_argument(
        "--headless",
        action="store_true",
        help=t("app.cli.headless_help"),
    )
    parser.add_argument(
        "--gallery",
        action="store_true",
        help=t("app.cli.gallery_help"),
    )
    parser.add_argument(
        "dataset_dir", nargs="?", help=t("app.cli.dataset_dir_help")
    )
    parser.add_argument("--out", default="curation_report.json", help=t("app.cli.out_help"))
    parser.add_argument(
        "--format",
        default="json",
        choices=("json", "md", "both"),
        help=t("app.cli.format_help"),
    )
    parser.add_argument(
        "--persistent-id", default="", help=t("app.cli.persistent_id_help")
    )
    parser.add_argument(
        "--export-record",
        action="store_true",
        help=t("app.cli.export_record_help"),
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help=t("app.cli.config_help"),
    )
    parser.add_argument(
        "--dataverse",
        default=None,
        help=t("app.cli.dataverse_help"),
    )
    args = parser.parse_args(argv)
    mark("args parsed")

    if args.headless:
        if not args.dataset_dir:
            parser.error(t("app.cli.headless_requires_dir"))
        if args.dataverse or args.config != "config.json":
            # Both flags are GUI-only (config/token/network); accepting them
            # here would silently ignore what the user asked for.
            parser.error(t("app.cli.headless_gui_only"))
        dataset_path = Path(args.dataset_dir)
        if not dataset_path.exists():
            parser.error(t("app.cli.dir_not_found", path=args.dataset_dir))
        if not dataset_path.is_dir():
            parser.error(t("app.cli.dir_not_a_directory", path=args.dataset_dir))
        out_path = Path(args.out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            parser.error(t("app.cli.cannot_create_output", exc=exc))
        from engine.runner import run_report_to_file

        try:
            report = run_report_to_file(
                dataset_path,
                out_path,
                persistent_id=args.persistent_id,
                fmt=args.format,
            )
        except Exception as exc:
            print(t("app.cli.run_failed", exc=exc), file=sys.stderr)
            return 2
        errors = sum(
            1
            for r in report.dataset_checks
            if r.level == "error" and not r.passed
        ) + sum(
            1
            for f in report.files
            for r in f.checks
            if r.level == "error" and not r.passed
        )
        warnings = sum(
            1
            for r in report.dataset_checks
            if r.level in {"warning", "error"} and not r.passed
        ) + sum(
            1
            for f in report.files
            for r in f.checks
            if r.level in {"warning", "error"} and not r.passed
        )
        written = str(out_path)
        if args.format == "both":
            sibling = out_path.with_suffix(".md" if out_path.suffix.lower() != ".md" else ".json")
            written = f"{out_path} + {sibling}"
        print(
            t(
                "app.cli.report_written",
                written=written,
                files=len(report.files),
                warnings=warnings,
            )
        )
        # One synthesized verdict line (dv-6nv); tokens, not copy.
        try:
            from engine.verdict import assess, format_line

            print(t("app.cli.verdict_line", verdict=format_line(assess(report))))
        except Exception:
            pass
        # Optional curation-record bundle (dv-vwt).
        if getattr(args, "export_record", False):
            try:
                from curation_record import export_record

                record_dir = export_record(
                    out_path.parent,
                    report=report,
                    staged_dir=dataset_path,
                )
                print(t("app.cli.record_written", path=str(record_dir)))
            except Exception as exc:
                print(t("app.cli.run_failed", exc=exc), file=sys.stderr)
                return 2
        # CI-usable exit code: 1 when error-level findings exist, 0 otherwise.
        # Warnings alone do not fail the run.
        return 1 if errors else 0

    from PySide6.QtWidgets import QApplication

    from config import Config
    from ui.main_window import MainWindow

    mark("PySide6 + ui.main_window imported")

    try:
        cfg = Config.load(Path(args.config))
    except ValueError as exc:
        # Corrupt config: fall back to defaults but tell the user loudly
        # instead of silently discarding their workspace/token.
        print(t("app.cli.config_warning", exc=exc), file=sys.stderr)
        from config import Config as _Config

        cfg = _Config()
    if args.dataverse:
        cfg.dataverse.base_url = args.dataverse.rstrip("/")
    mark("config loaded")

    app = QApplication(sys.argv)
    mark("QApplication created")
    try:
        from PySide6.QtGui import QIcon

        from ui.theme import mark_icon_path

        # Taskbar/dock icon: the 16x16 mark (the About page keeps docent.png).
        _icon_path = mark_icon_path()
        if _icon_path:
            app.setWindowIcon(QIcon(_icon_path))
    except Exception:
        pass
    try:
        from ui.theme import apply_theme
        apply_theme(app)
    except Exception:
        pass
    mark("theme applied")

    if args.gallery:
        # The component gallery needs no server, token or workspace: it
        # shows the kit, not the data.
        from ui.gallery import build_gallery

        gallery = build_gallery()
        gallery.show()
        mark("gallery shown")
        return app.exec()

    # Global crash guard — show a copyable dialog instead of silently exiting
    def _excepthook(exc_type, exc, tb):
        import traceback

        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            from ui.dialogs import show_critical

            show_critical(None, t("app.unexpected_error"), msg)
        except Exception:
            print(msg, file=sys.stderr)

    sys.excepthook = _excepthook

    window = MainWindow(cfg)
    mark("MainWindow constructed")
    window.show()
    mark("window shown")
    # The window is created cloaked: paint the shell, then reveal it in one
    # step so no empty client or native caption can flash. Cached rows, local
    # state and the first crawl follow (background load), after this point.
    app.processEvents()
    window.reveal()
    mark("first paint")
    window.start_background_load()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
