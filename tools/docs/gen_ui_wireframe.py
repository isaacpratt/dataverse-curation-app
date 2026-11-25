"""Generate the numbered UI wireframe and its technical legend.

This is a UI harness in the same family as ``tools/probes`` (hence the
import-linter exception): it boots the real app offscreen, walks the live
widget tree, and measures actual geometry, ``objectName`` values, layout
managers and size policies. The published SVG and Markdown are therefore a
map of the running app, not a hand-maintained guess.

Usage::

    uv run python tools/docs/gen_ui_wireframe.py --check
    uv run python tools/docs/gen_ui_wireframe.py --write

The check mode regenerates in memory and compares against the committed
files; the pytest guard in ``tools/tests/test_ui_wireframe.py`` validates
the committed pair without needing Qt (so it runs on any machine).
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SVG_PATH = ROOT / "docs" / "assets" / "ui-wireframe.svg"
DOC_PATH = ROOT / "docs" / "reference" / "ui-wireframe.md"
BEGIN = "<!-- BEGIN GENERATED UI WIREFRAME -->"
END = "<!-- END GENERATED UI WIREFRAME -->"

# Stable workspace path: a random temp path would leak into rendered labels
# and make two otherwise identical runs produce different SVG bytes.
WORKSPACE = Path(tempfile.gettempdir()) / "docent-wireframe-workspace"

# The canvas is 1280 px wide in the app; the SVG scales it to 576 units so a
# whole screen fits beside its numbered gutter in a two-column page.
SCALE = 0.45
PANEL_W = 720
PANEL_H = 410
CANVAS_W = 576
CANVAS_H = 387
GUTTER_X = 600
GUTTER_W = 110


@dataclass(frozen=True)
class Landmark:
    """One numbered [NN] callout in the diagram."""

    tag: str
    screen: str
    name: str
    class_name: str
    object_name: str
    layout: str
    size_policy: str
    bounds: str
    note: str


@dataclass(frozen=True)
class Screen:
    """A captured screen and the landmarks drawn for it."""

    title: str
    width: int
    height: int
    landmarks: tuple[Landmark, ...]


@dataclass(frozen=True)
class Spec:
    """What to look for on a screen: objectName, friendly name, note."""

    object_name: str
    name: str
    note: str = ""


# Curated landmarks per screen. Every number is stable: tags are assigned by
# registry order after collection, so regenerating cannot renumber a callout
# that a reader already learned. The names are the roles a curator would use.
SCREENS: tuple[tuple[str, tuple[Spec, ...]], ...] = (
    (
        "Main window / dashboard",
        (
            Spec("TopNav", "Top nav bar", "fixed 48 px high chrome; sits above the page stack"),
            Spec("NavActive", "Active nav button", "selected state; 32 px high"),
            Spec("NavItem", "Nav button", "one per pane; same 32 px height"),
            Spec("ChipsWrap", "Chip row", "Expanding/Preferred; wraps chips"),
            Spec("WinControls", "Window controls", "fixed-width right edge of the nav bar"),
            Spec("DashboardView", "Dashboard page", "background of the stacked page"),
            Spec("MetricCard", "Metric card", "three across; one per queue metric"),
            Spec("Card", "Queue card", "contains the header and the table"),
            Spec("QueueHeaderBar", "Queue header", "headline plus filter row"),
            Spec("QueueStack", "Queue table", "grid layout; one row per dataset"),
            Spec("StatusPill", "Status pill", "bottom status strip"),
            Spec("RingProgress", "Progress ring", "busy indicator inside the status pill"),
            Spec("DocentMark", "Docent mark", "watermark at the bottom-right"),
        ),
    ),
    (
        "Dataset detail",
        (
            Spec("DetailView", "Detail page", "root of the detail view"),
            Spec(
                "DetailTopBar", "Detail header", "fixed 170 px; scrolls away with the main column"
            ),
            Spec("WorkflowRail", "Workflow rail", "step buttons; fixed 36 px high"),
            Spec("WorkflowStep", "Workflow step", "done/active/blocked states"),
            Spec("FilterChip", "Filter chip", "chip family; 36 px high"),
            Spec("PillInReview", "Review state pill", "conditional: IN REVIEW only"),
            Spec("PillDraft", "Draft state pill", "conditional: DRAFT only"),
            Spec("PrimaryButton", "Primary action button", "commit / approve"),
            Spec("SecondaryButton", "Secondary action button", "download, export, back"),
            Spec("HeadlineLG", "Dataset title", "large headline"),
            Spec("BodyMD", "Dataset subtitle", "PID and owner line"),
            Spec("StatusWidget", "Status widget", "info/success/error states"),
            Spec("DetailPages", "Page stack", "review page and response page"),
            Spec("DetailReviewPage", "Review page", "main column plus sidebar"),
            Spec("DetailMainContainer", "Main column", "scroll canvas for cards"),
            Spec("DetailSideContainer", "Sidebar", "280-400 px; horizontal scrollbar off"),
            Spec("Card", "Detail card", "metadata, files, checks, sensitivity"),
        ),
    ),
    (
        "Settings",
        (
            Spec("SettingsDialog", "Settings pane", "root of the settings form"),
            Spec("HeadlineLG", "Settings heading", "large headline"),
            Spec("BodyMD", "Settings help text", "body copy"),
            Spec("Card", "Settings card", "grouped form controls"),
            Spec("SearchField", "Search field", "line edit with a search icon"),
            Spec("LabelStrongSM", "Field label", "small strong label"),
            Spec("SecondaryButton", "Cancel button", "discard path"),
            Spec("PrimaryButton", "Save button", "commit path"),
            Spec("PaneFooter", "Pane footer", "fixed action strip"),
        ),
    ),
    (
        "About",
        (
            Spec("AboutPane", "About pane", "root of the About page"),
            Spec("HeadlineLG", "About heading", "large headline"),
            Spec("Card", "About card", "version and attribution"),
            Spec("DocentMark", "Docent mark", "brand glyph"),
            Spec("UpdatesCard", "Updates card", "last-checked state is conditional"),
            Spec("UpdatesDivider", "Updates divider", "separates actions"),
            Spec("SecondaryButton", "Check for updates", "disabled while a check runs"),
        ),
    ),
    (
        "Log",
        (
            Spec("LogPage", "Log page", "root of the app request log"),
            Spec("HeadlineLG", "Log heading", "large headline"),
            Spec("SearchField", "Log search", "filters request lines"),
            Spec("SecondaryButton", "Log action", "clear / export controls"),
        ),
    ),
    (
        "Review configuration",
        (
            Spec("ReviewConfigView", "Review config page", "root of the ruleset editor"),
            Spec("HeadlineLG", "Config heading", "large headline"),
            Spec("Card", "Ruleset card", "one per configured ruleset"),
            Spec("CardTopBar", "Card top bar", "title plus row actions"),
            Spec("CardTitle", "Card title", "ruleset name"),
            Spec("CardBodyWrap", "Card body", "parameter controls"),
            Spec("SearchField", "Config search", "line edit"),
            Spec("SecondaryButton", "Config action", "run / edit controls"),
        ),
    ),
    (
        "Component gallery",
        (
            Spec("GalleryWindow", "Gallery window", "root of the component gallery"),
            Spec("HeadlineLG", "Gallery heading", "large headline"),
            Spec("BodyMD", "Gallery subtitle", "body copy"),
            Spec("GalleryContent", "Gallery content", "scrollable body"),
            Spec("GalleryDualTheme", "Dual-theme view", "light and dark side by side"),
            Spec("GalleryThemeColumn", "Theme column", "one per rendered theme"),
        ),
    ),
)


def _find(root: Any, object_name: str) -> Any | None:
    """First visible widget with ``object_name`` under ``root``."""
    from PySide6.QtWidgets import QWidget

    for widget in root.findChildren(QWidget):
        if widget.objectName() == object_name and widget.isVisible():
            geometry = widget.geometry()
            if geometry.width() > 0 and geometry.height() > 0:
                return widget
    if root.objectName() == object_name and root.isVisible():
        return root
    return None


def _policy(widget: Any) -> str:
    policy = widget.sizePolicy()
    horizontal = policy.horizontalPolicy().name
    vertical = policy.verticalPolicy().name
    return f"{horizontal}/{vertical}" if horizontal != vertical else horizontal


def _bounds(widget: Any, root: Any) -> str:
    geometry = widget.geometry()
    origin = root.geometry()
    # A window root's frame origin is offset by 2 px; clamp so a child at the
    # top-left reads 0,0 rather than a confusing -2,-2.
    x = max(geometry.x() - origin.x(), 0)
    y = max(geometry.y() - origin.y(), 0)
    return f"{x},{y} {geometry.width()},{geometry.height()}"


def _capture(root: Any, title: str, specs: tuple[Spec, ...]) -> Screen:
    """Measure every curated landmark on one screen."""
    geometry = root.geometry()
    landmarks: list[Landmark] = []
    for spec in specs:
        widget = _find(root, spec.object_name)
        if widget is None:
            # A missing landmark is a real gap in the map: say so in the
            # legend instead of silently dropping a numbered callout.
            landmarks.append(
                Landmark(
                    "",
                    title,
                    spec.name,
                    "—",
                    spec.object_name,
                    "—",
                    "—",
                    "not present in this screen",
                    spec.note,
                )
            )
            continue
        layout = widget.layout()
        landmarks.append(
            Landmark(
                "",
                title,
                spec.name,
                type(widget).__name__,
                spec.object_name,
                type(layout).__name__ if layout is not None else "—",
                _policy(widget),
                _bounds(widget, root),
                spec.note,
            )
        )
    return Screen(title, geometry.width(), geometry.height(), tuple(landmarks))


def _settle(app: Any, cycles: int = 8) -> None:
    """Let queued layout and stylesheet work finish before measuring."""
    for _ in range(cycles):
        app.processEvents()


def _make_detail(config: Any) -> Any:
    """Build the seeded detail view used by the diagram (no network)."""
    from ui.dataset import DatasetDetailView

    metadata = {
        "id": 1,
        "latestVersion": {
            "versionState": "DRAFT",
            "metadataBlocks": {"citation": {"fields": [{"typeName": "title", "value": "A study"}]}},
        },
    }
    detail = DatasetDetailView(
        config,
        "doi:10.5072/FK2/WIREFRAME",
        "A study",
        cached_metadata=metadata,
        cached_inventory=[],
    )
    detail.resize(1280, 900)
    detail.show()
    return detail


def _open_pane(window: Any, title: str) -> Any:
    """Switch the main window to one of its non-dashboard panes."""
    key = {
        "Settings": "settings",
        "About": "about",
        "Log": "log",
        "Review configuration": "review-config",
    }[title]
    if key == "review-config":
        window._show_review_config()
    else:
        window._show_pane(key)
    return window._stack.currentWidget()


def _renumber(screens: list[Screen]) -> list[Screen]:
    """Assign stable [NN] tags in registry order."""
    counter = 1
    numbered: list[Screen] = []
    for screen in screens:
        landmarks: list[Landmark] = []
        for landmark in screen.landmarks:
            tag = f"[{counter:02d}]"
            counter += 1
            landmarks.append(
                Landmark(
                    tag,
                    landmark.screen,
                    landmark.name,
                    landmark.class_name,
                    landmark.object_name,
                    landmark.layout,
                    landmark.size_policy,
                    landmark.bounds,
                    landmark.note,
                )
            )
        numbered.append(Screen(screen.title, screen.width, screen.height, tuple(landmarks)))
    return numbered


def collect() -> list[Screen]:
    """Boot the app offscreen and measure every screen in ``SCREENS``."""
    import shutil

    from PySide6.QtWidgets import QApplication

    from curation.config import Config
    from ui.dataset import DatasetDetailView
    from ui.gallery import build_gallery
    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Qt 6 ships no fonts; pin the platform face before the app exists so
    # measured geometry matches what a user sees.
    if not os.environ.get("QT_QPA_FONTDIR"):
        font_dir = (
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            if sys.platform.startswith("win")
            else "/usr/share/fonts"
        )
        if os.path.isdir(font_dir):
            os.environ["QT_QPA_FONTDIR"] = font_dir

    shutil.rmtree(WORKSPACE, ignore_errors=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    apply_theme(app)  # type: ignore[arg-type]
    config = Config()
    config.app.workspace = WORKSPACE

    # No network: a detail view created for the diagram must not fetch.
    original_load = DatasetDetailView._on_load_metadata
    DatasetDetailView._on_load_metadata = lambda self: None  # type: ignore[method-assign]
    try:
        window = MainWindow(config)
        window.resize(1280, 860)
        window.show()
        _settle(app, 10)

        captured: dict[str, Screen] = {}
        for title, specs in SCREENS:
            if title == "Dataset detail":
                root = _make_detail(config)
            elif title == "Component gallery":
                root = build_gallery()
                root.show()
            elif title == "Main window / dashboard":
                root = window
            else:
                root = _open_pane(window, title)
            _settle(app)
            captured[title] = _capture(root, title, specs)

        return _renumber([captured[title] for title, _ in SCREENS])
    finally:
        DatasetDetailView._on_load_metadata = original_load  # type: ignore[method-assign]
        shutil.rmtree(WORKSPACE, ignore_errors=True)


def _svg_box(
    x: int, y: int, width: int, height: int, screen: Screen
) -> tuple[float, float, float, float]:
    """Scale a widget's bounds into a panel's canvas, clamped to the screen."""
    sx = min(max(x, 0), screen.width) * SCALE
    sy = min(max(y, 0), screen.height) * SCALE
    sw = max(width, 2) * SCALE
    sh = max(height, 2) * SCALE
    return (
        round(sx, 1),
        round(sy, 1),
        round(min(sw, CANVAS_W - sx), 1),
        round(min(sh, CANVAS_H - sy), 1),
    )


def render_svg(screens: list[Screen]) -> str:
    """Return the complete wireframe SVG as diffable text.

    Presentation attributes are written explicitly rather than relying on a
    CSS ``<style>`` block: Qt's SVG renderer ignores class selectors, and the
    diagram must be legible in the docs site *and* in a Qt-rendered preview.
    """
    rows = (len(screens) + 1) // 2
    height = rows * (PANEL_H + 24) + 24
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1480 '
        f'{height}" width="1480" height="{height}" role="img" '
        'aria-labelledby="wireframe-title">',
        '  <title id="wireframe-title">Numbered UI wireframe of Dataverse Docent</title>',
        "  <!-- Generated by tools/docs/gen_ui_wireframe.py; edit the generator, not this file. -->",
    ]
    for index, screen in enumerate(screens):
        column, row = index % 2, index // 2
        px = 8 + column * (PANEL_W + 16)
        py = 8 + row * (PANEL_H + 24)
        lines.append(f'  <g transform="translate({px} {py})">')
        lines.append(
            f'    <rect class="panel" x="0" y="0" width="{PANEL_W}" height="{PANEL_H}" '
            'rx="8" fill="#f7f8fa" stroke="#d7dae0" stroke-width="1"/>'
        )
        lines.append(
            '    <text class="title" x="12" y="22" font-family="Arial, sans-serif" '
            f'font-size="15" font-weight="600" fill="#1f2937">{html.escape(screen.title)}</text>'
        )
        lines.append(
            '    <text class="hint" x="12" y="38" font-family="Arial, sans-serif" '
            f'font-size="11" fill="#5b6472">canvas {screen.width}x{screen.height} '
            f"at {int(SCALE * 100)}%</text>"
        )
        lines.append(
            f'    <rect class="canvas" x="12" y="46" width="{CANVAS_W}" '
            f'height="{CANVAS_H}" rx="2" fill="#ffffff" stroke="#d7dae0" stroke-width="1"/>'
        )
        lines.append('    <g transform="translate(12 46)">')
        kit = screen.title == "Component gallery"
        seen: set[tuple[float, float, float, float]] = set()
        for landmark in screen.landmarks:
            if landmark.bounds.startswith("not present"):
                continue
            values = landmark.bounds.replace(",", " ").split()
            if len(values) < 4:
                continue
            try:
                x, y, width, height = (int(value) for value in values[:4])
            except ValueError:
                continue
            bx, by, bw, bh = _svg_box(x, y, width, height, screen)
            key = (bx, by, bw, bh)
            if key in seen:
                continue
            seen.add(key)
            fill, stroke = ("#eaf5ee", "#2f6b43") if kit else ("#e8eef7", "#3d5a80")
            lines.append(
                f'      <rect class="box" x="{bx}" y="{by}" width="{bw}" '
                f'height="{bh}" rx="2" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="1.2"><title>{html.escape(landmark.tag + " " + landmark.name)}</title></rect>'
            )
        lines.append("    </g>")
        # Tags live in a right-hand gutter, so the label text never changes
        # the proportions of the boxes it names.
        visible = [
            landmark
            for landmark in screen.landmarks
            if not landmark.bounds.startswith("not present")
        ]
        if visible:
            spacing = (CANVAS_H - 20) / max(len(visible), 1)
            for slot, landmark in enumerate(visible):
                ty = 52 + slot * spacing
                lines.append(
                    f'    <line class="leader" x1="{12 + CANVAS_W}" y1="{round(ty + 6, 1)}" '
                    f'x2="{GUTTER_X}" y2="{round(ty + 6, 1)}" '
                    'stroke="#8a93a4" stroke-width="0.8"/>'
                )
                lines.append(
                    f'    <text class="tag" data-tag="{landmark.tag}" x="{GUTTER_X + 4}" '
                    f'y="{round(ty + 6, 1)}" font-family="Arial, sans-serif" '
                    f'font-size="11" font-weight="600" fill="#1f2937">'
                    f"{landmark.tag} {html.escape(landmark.name)}</text>"
                )
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_legend(screens: list[Screen]) -> str:
    """Return the generated Markdown block: one table row per numbered tag."""
    lines = [
        BEGIN,
        "",
        "| Tag | Screen | Element | Qt class | objectName | Layout | Size policy | Bounds (x,y w,h) | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for screen in screens:
        for landmark in screen.landmarks:
            cells = (
                landmark.tag,
                landmark.screen,
                landmark.name,
                landmark.class_name,
                f"`{landmark.object_name}`",
                landmark.layout,
                landmark.size_policy,
                landmark.bounds,
                landmark.note,
            )
            lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    lines.extend(["", END])
    return "\n".join(lines)


PAGE_TEMPLATE = """---
page_type: reference
tgdp_template: Reference
audience: developer
---
# UI wireframe reference

Numbered map of the painted app. Each `[NN]` badge in [the SVG](../assets/ui-wireframe.svg) names one box; the legend below gives its Qt class, `objectName` (the QSS selector and `findChild` key), layout manager, size policy and measured bounds. Tags sit in a gutter beside the boxes so the labels never distort the proportions they describe. For the rules behind the layout, see [UI conventions](../explanation/ui-conventions.md).

{block}

## Non-visible states

A static image cannot show a state that is not active while it is captured. These are the conditional states to check when a screenshot looks right but behaviour is wrong; the object names are the same ones in the legend.

| Family | objectName / QSS selector | Loading | Empty | Error | Disabled | Hover / focus |
| --- | --- | --- | --- | --- | --- | --- |
| Buttons | `#PrimaryButton`, `#SecondaryButton`, `#NavActive`, `#NavItem` | `setEnabled(False)` while a worker runs; `AppButton` keeps its height (32/36/40 px) | n/a — a button always renders | status text moves to `#StatusWidget`; the button itself is not an error surface | `setEnabled(False)`; QSS dims the face but keeps the outline | `#AppButton:hover` raises the surface; focus draws the accent ring |
| Chips | `#FilterChip`, `#ChipsWrap`, `#StatusWidget` | chip text is replaced with the phase message; `Expanding/Preferred` wrap keeps its row | placeholder text in the status widget | `#StatusWidget.set_error` paints the error tone and keeps the detail in the tooltip | no dedicated disabled chip; hide the chip instead | chip buttons follow the same `:hover` / `:focus` rules as buttons |
| Cards | `#Card`, `#MetricCard`, `#UpdatesCard` | card body shows a placeholder until its worker finishes | `#Card` keeps its frame and shows the empty-state label instead of rows | the card stays and the status widget carries the error; no card is deleted | controls inside the card are disabled individually | cards themselves do not take hover; only their controls do |
| Workflow rail | `#WorkflowRail`, `#WorkflowStep` | current step keeps its badge; later steps stay dimmed | n/a | a blocked step wears the lock mark (state is not colour-only) | unavailable steps are non-clickable | hover reveals the step tooltip; focus ring follows the button rules |

## Bounding-box constraints

These are the constraints that cause clipping and overlap. They are read from the running widgets (geometry, size policies and scroll areas), not inferred from the picture.

| Container | Fixed dimensions | Size policy | Overflow rule | Stacking (z-order) |
| --- | --- | --- | --- | --- |
| `#TopNav` | 48 px high (`setFixedHeight(48)`); nav buttons 32 px | `Preferred/Preferred`, `#ChipsWrap` `Expanding/Preferred` | chip row wraps; window controls keep a fixed 144 px edge | nav bar paints above the page stack |
| `#DetailTopBar` | 170 px tall in the captured layout; headline and status share the row | `Preferred/Preferred` | text elides (`#LabelMD`, `ElidedLabel`); status detail lines clip rather than wrap the header | header scrolls with the main column, below any popup |
| `#WorkflowRail` | steps fixed 36 px high (`BUTTON_HEIGHTS["md"]`) | `Fixed/Fixed` per step | horizontal rail; a long workflow scrolls, it does not wrap | rail sits above the page body inside the header |
| `#DetailSideContainer` | side scroll area min 280 px, max 400 px wide | `Preferred/Preferred` | horizontal scrollbar always off; vertical scrollbar owns overflow | sidebar is a sibling of the main column, never overlaps it |
| `#Card`, `#MetricCard` | metric cards 52 px high; chip/button heights 36 px | `Preferred/Preferred` | long labels elide; the card frame is not resized by its text | cards are painted in document order inside their scroll canvas |
| `#StatusWidget` | status detail fixed to the right edge of the strip | `Expanding/Fixed` on the caption | caption elides; error detail stays in the tooltip | strip is at the bottom of the page, below dialogs |

## Regenerate

```bash
uv run python tools/docs/gen_ui_wireframe.py --write   # regenerate SVG + legend
uv run python tools/docs/gen_ui_wireframe.py --check   # fail if stale
```

The generator boots the app offscreen against a throwaway workspace (never the configured instance), walks the real widget tree, and writes text-only SVG and Markdown. It assigns tags in registry order, so a published tag keeps its number across runs. `tools/tests/test_ui_wireframe.py` checks that every badge in the SVG has exactly one legend row, that no number is reused, and that the state and constraint tables are present — without needing Qt.
"""


def check() -> bool:
    """Return True when both committed files match a fresh capture."""
    screens = collect()
    svg_ok = SVG_PATH.exists() and SVG_PATH.read_text(encoding="utf-8") == render_svg(screens)
    doc_ok = DOC_PATH.exists() and DOC_PATH.read_text(encoding="utf-8") == PAGE_TEMPLATE.format(
        block=render_legend(screens)
    )
    return svg_ok and doc_ok


def write() -> tuple[bool, bool]:
    """Regenerate both files; return (svg_changed, doc_changed)."""
    screens = collect()
    svg = render_svg(screens)
    doc = PAGE_TEMPLATE.format(block=render_legend(screens))
    svg_changed = not SVG_PATH.exists() or SVG_PATH.read_text(encoding="utf-8") != svg
    doc_changed = not DOC_PATH.exists() or DOC_PATH.read_text(encoding="utf-8") != doc
    if svg_changed:
        SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SVG_PATH.write_text(svg, encoding="utf-8", newline="\n")
    if doc_changed:
        DOC_PATH.write_text(doc, encoding="utf-8", newline="\n")
    return svg_changed, doc_changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail when a file is stale")
    group.add_argument("--write", action="store_true", help="regenerate both files")
    args = parser.parse_args(argv)
    if args.write:
        svg_changed, doc_changed = write()
        print(
            "UI wireframe: "
            f"SVG {'updated' if svg_changed else 'current'}, "
            f"legend {'updated' if doc_changed else 'current'}"
        )
        return 0
    if check():
        print("UI wireframe: OK")
        return 0
    print(
        "UI wireframe: stale — run `uv run python tools/docs/gen_ui_wireframe.py --write`",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
