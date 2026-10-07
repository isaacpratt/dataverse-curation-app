"""Launch the Dataverse Docent entry point.

Default is the desktop GUI; --headless runs the engine on a staged
dataset directory and writes a JSON report (see docs/html/development.html).
"""

import argparse
import sys
from pathlib import Path


def _sibling_libs_path() -> Path | None:
    """Find a sibling full-build libs folder next to a frozen exe.

    Looks for `curation-app-full/` next to the exe (onefile layout: exe in
    `dist/`, full folder beside it) or next to the folder holding the exe
    (onedir layout: `dist/curation-app-lite/curation-app-lite.exe`, full
    folder in `dist/`) and returns its path. The folder should be an onedir
    PyInstaller build (or just a Python site-packages tree) — anything we
    can prepend to sys.path to load the heavy optional libraries (pyreadstat,
    netCDF4, h5py, …) without re-bundling them in the lite build. The lite
    exe remains self-contained; the sibling folder is purely additive.
    """
    if not getattr(sys, "frozen", False):
        return None
    # NOTE: sys._MEIPASS is deliberately NOT used here — in onefile mode it
    # is a temp extraction dir (whose parent is meaningless), and in onedir
    # mode it is the _internal folder. The sibling folder always lives next
    # to the real .exe, or next to the folder containing it (onedir).
    exe_dir = Path(sys.executable).parent
    for base in (exe_dir, exe_dir.parent):
        candidate = base / "curation-app-full"
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return None


def _inject_sibling_libs() -> int:
    """Prepend the sibling libs folder to sys.path.

    Returns the number of new path entries added (0 if none / not frozen).
    """
    folder = _sibling_libs_path()
    if folder is None:
        return 0
    added = 0
    # Precedence first: the onedir _internal dir (where PyInstaller v5+
    # puts top-level packages), then a plain site-packages layout, then the
    # folder root itself last (lowest precedence — never shadow stdlib).
    for sub in (folder / "_internal", folder / "Lib" / "site-packages", folder):
        try:
            if sub.exists() and str(sub) not in sys.path:
                if sub == folder:
                    sys.path.append(str(sub))
                else:
                    sys.path.insert(0, str(sub))
                added += 1
        except Exception:
            pass
    return added


# Ensure PyInstaller bundles the GUI even though it is imported lazily
# inside main() (so --headless can run without a display).
# These imports are TYPE_CHECKING-only at runtime to keep --headless fast
# (~300ms + ~100MB saved by not loading Qt). PyInstaller still discovers
# them via the explicit hidden-imports in the spec / Makefile.
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
    parser = argparse.ArgumentParser(description="Dataverse Docent")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run checks on a local directory and write a JSON report",
    )
    parser.add_argument(
        "dataset_dir", nargs="?", help="staged dataset directory (headless mode)"
    )
    parser.add_argument("--out", default="curation_report.json", help="output report path")
    parser.add_argument(
        "--format",
        default="json",
        choices=("json", "md", "both"),
        help="report format: json, md, or both (default: json)",
    )
    parser.add_argument("--persistent-id", default="", help="dataset persistent ID")
    parser.add_argument(
        "--config",
        default="config.json",
        help="path to config.json (default: ./config.json)",
    )
    parser.add_argument(
        "--dataverse",
        default=None,
        help="override dataverse base URL (e.g. https://demo.borealisdata.ca)",
    )
    args = parser.parse_args(argv)

    # In frozen builds, look for a sibling `curation-app-full/` folder and
    # prepend it to sys.path so heavy libs (pyreadstat, netCDF4, h5py, …)
    # load without re-bundling them in the lite exe. Quiet unless found.
    if getattr(sys, "frozen", False):
        _inject_sibling_libs()

    if args.headless:
        if not args.dataset_dir:
            parser.error("headless mode requires a dataset_dir")
        if args.dataverse or args.config != "config.json":
            # Both flags are GUI-only (config/token/network); accepting them
            # here would silently ignore what the user asked for.
            parser.error("--dataverse/--config are GUI-only and ignored in headless mode")
        dataset_path = Path(args.dataset_dir)
        if not dataset_path.exists():
            parser.error(f"dataset_dir not found: {args.dataset_dir}")
        if not dataset_path.is_dir():
            parser.error(f"dataset_dir is not a directory: {args.dataset_dir}")
        out_path = Path(args.out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            parser.error(f"cannot create output directory ({exc})")
        from engine.runner import run_report_to_file

        try:
            report = run_report_to_file(
                dataset_path,
                out_path,
                persistent_id=args.persistent_id,
                fmt=args.format,
            )
        except Exception as exc:
            print(f"headless run failed: {exc}", file=sys.stderr)
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
        print(f"Report written to {written} ({len(report.files)} files, {warnings} finding(s))")
        # CI-usable exit code: 1 when error-level findings exist, 0 otherwise.
        # Warnings alone do not fail the run.
        return 1 if errors else 0

    from PySide6.QtWidgets import QApplication

    from config import Config
    from ui.main_window import MainWindow

    try:
        cfg = Config.load(Path(args.config))
    except ValueError as exc:
        # Corrupt config: fall back to defaults but tell the user loudly
        # instead of silently discarding their workspace/token.
        print(f"config warning: {exc} — using defaults", file=sys.stderr)
        from config import Config as _Config

        cfg = _Config()
    if args.dataverse:
        cfg.dataverse.base_url = args.dataverse.rstrip("/")

    app = QApplication(sys.argv)
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

    # Global crash guard — show a copyable dialog instead of silently exiting
    def _excepthook(exc_type, exc, tb):
        import traceback

        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            from ui.dialogs import show_critical

            show_critical(None, "Unexpected error", msg)
        except Exception:
            print(msg, file=sys.stderr)

    sys.excepthook = _excepthook

    window = MainWindow(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
