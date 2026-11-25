"""Generate the numbered UI wireframe: annotated screenshots + clean schematics.

This is a UI harness in the same family as ``tools/probes`` (hence the
import-linter exception): it boots the real app offscreen, captures a full
screenshot of every screen, and measures the live widget tree. The published
SVG pairs each captured screen with a vector schematic of the same widgets;
both halves use the same ``[NN]`` numbers, a highlight on the exact bounds and
a leader line that ends on the widget it names.

Usage::

    uv run python tools/docs/gen_ui_wireframe.py --check
    uv run python tools/docs/gen_ui_wireframe.py --write

The check mode regenerates in memory and compares against the committed
files; the pytest guard in ``tools/tests/test_ui_wireframe.py`` validates the
committed pair without needing Qt (so it runs on any machine).
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
ASSET_DIR = ROOT / "docs" / "assets" / "wireframe"
DOC_PATH = ROOT / "docs" / "reference" / "ui-wireframe.md"
BEGIN = "<!-- BEGIN GENERATED UI WIREFRAME -->"
END = "<!-- END GENERATED UI WIREFRAME -->"

# Stable workspace path: a random temp path would leak into rendered labels
# and make two otherwise identical runs produce different SVG bytes.
WORKSPACE = Path(tempfile.gettempdir()) / "docent-wireframe-workspace"

# Page geometry. Each screen owns one row: captured view left, schematic right.
VIEW_W = 1480
PANEL_W = 720
PANEL_H = 470
ROW_H = PANEL_H + 16
CANVAS_W = 700
CANVAS_H = 420
FONT = "Arial, sans-serif"  # Qt's SVG renderer substitutes badly on system-ui

BUTTON_NAMES = frozenset(
    {
        "NavActive",
        "NavItem",
        "WorkflowStep",
        "FilterChip",
        "PrimaryButton",
        "SecondaryButton",
        "IconButton",
        "RefreshButton",
    }
)
CHIP_HINTS = ("Chip", "Pill", "Badge", "StatusPill")
# Wide wrappers are containers, even when their name contains "Chip".
CONTAINER_OVERRIDES = frozenset({"ChipsWrap", "CardBodyWrap", "CardTopBar"})
CARD_NAMES = frozenset({"Card", "MetricCard", "UpdatesCard", "CardTopBar"})
TEXT_NAMES = frozenset(
    {
        "HeadlineLG",
        "HeadlineMD",
        "HeadlineSM",
        "BodyMD",
        "BodySM",
        "LabelMD",
        "LabelSM",
        "LabelStrongSM",
        "CaptionSM",
        "HintSM",
        "StateMD",
        "MonoSM",
        "ValueMD",
        "CardTitle",
        "DocentMark",
    }
)


@dataclass(frozen=True)
class Landmark:
    """One numbered [NN] callout, shared by both panels."""

    tag: str
    screen: str
    name: str
    class_name: str
    object_name: str
    layout: str
    size_policy: str
    bounds: str
    note: str
    kind: str


@dataclass(frozen=True)
class Screen:
    """A captured screen, its image and the landmarks drawn on both panels."""

    key: str
    title: str
    width: int
    height: int
    image: str
    landmarks: tuple[Landmark, ...]


@dataclass(frozen=True)
class Spec:
    """What to look for on a screen: objectName, friendly name, note."""

    object_name: str
    name: str
    note: str = ""


SCREENS: tuple[tuple[str, str, tuple[Spec, ...]], ...] = (
    (
        "dashboard",
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
        "detail-review",
        "Dataset detail / review page",
        (
            Spec("DetailView", "Detail page", "root of the detail view"),
            Spec("DetailTopBar", "Detail header", "fixed 170 px; scrolls with the main column"),
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
        "detail-response",
        "Dataset detail / response page",
        (
            Spec("DetailView", "Detail page", "root of the detail view"),
            Spec("DetailTopBar", "Detail header", "shared by both pages"),
            Spec("WorkflowRail", "Workflow rail", "response step active"),
            Spec("FilterChip", "Filter chip", "chip family"),
            Spec("StatusWidget", "Status widget", "info/success/error states"),
            Spec("DetailResponsePage", "Response page", "scrollable draft editor"),
            Spec("DetailResponseInner", "Response inner", "full content inside the scroll area"),
            Spec("BodySM", "Response intro", "body copy"),
            Spec("Card", "Response card", "findings and draft sections"),
        ),
    ),
    (
        "settings",
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
        "about",
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
        "log",
        "Log",
        (
            Spec("LogPage", "Log page", "root of the app request log"),
            Spec("HeadlineLG", "Log heading", "large headline"),
            Spec("SearchField", "Log search", "filters request lines"),
            Spec("SecondaryButton", "Log action", "clear / export controls"),
        ),
    ),
    (
        "review-config",
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
        "gallery",
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


def _kind(spec: Spec, class_name: str) -> str:
    """Pick a schematic shape family for one landmark."""
    name = spec.object_name
    if name in CONTAINER_OVERRIDES:
        return "container"
    if name in BUTTON_NAMES:
        return "button"
    if any(hint in name for hint in CHIP_HINTS):
        return "chip"
    if name in CARD_NAMES or (class_name in {"QFrame", "QWidget"} and "Card" in name):
        return "card"
    if name in TEXT_NAMES or class_name.endswith("Label"):
        return "text"
    return "container"


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


def _capture(root: Any, key: str, title: str, specs: tuple[Spec, ...]) -> Screen:
    """Save the full screen and measure every curated landmark on it."""
    geometry = root.geometry()
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    image_path = ASSET_DIR / f"{key}.png"
    assert root.grab().save(str(image_path)), f"could not capture {key}"

    landmarks: list[Landmark] = []
    for spec in specs:
        widget = _find(root, spec.object_name)
        if widget is None:
            # A hidden conditional widget keeps its number in the legend and
            # is explicitly marked instead of silently vanishing.
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
                    _kind(spec, "—"),
                )
            )
            continue
        layout = widget.layout()
        class_name = type(widget).__name__
        landmarks.append(
            Landmark(
                "",
                title,
                spec.name,
                class_name,
                spec.object_name,
                type(layout).__name__ if layout is not None else "—",
                _policy(widget),
                _bounds(widget, root),
                spec.note,
                _kind(spec, class_name),
            )
        )
    return Screen(
        key, title, geometry.width(), geometry.height(), f"wireframe/{key}.png", tuple(landmarks)
    )


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
                    landmark.kind,
                )
            )
        numbered.append(
            Screen(
                screen.key,
                screen.title,
                screen.width,
                screen.height,
                screen.image,
                tuple(landmarks),
            )
        )
    return numbered


def collect() -> list[Screen]:
    """Boot the app offscreen, capture every screen and measure its widgets."""
    import shutil

    from PySide6.QtWidgets import QApplication

    from curation.config import Config
    from ui.dataset import DatasetDetailView
    from ui.gallery import build_gallery
    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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

        detail = _make_detail(config)
        captured: dict[str, Screen] = {}
        for key, title, specs in SCREENS:
            if key == "dashboard":
                root = window
            elif key == "detail-response":
                detail._show_response_page()
                root = detail
            elif key == "detail-review":
                detail._show_review_page()
                root = detail
            elif key == "gallery":
                root = build_gallery()
                root.show()
            else:
                root = _open_pane(window, title)
            _settle(app)
            captured[key] = _capture(root, key, title, specs)

        return _renumber([captured[key] for key, _, _ in SCREENS])
    finally:
        DatasetDetailView._on_load_metadata = original_load  # type: ignore[method-assign]
        shutil.rmtree(WORKSPACE, ignore_errors=True)


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    values = bounds.replace(",", " ").split()
    if len(values) < 4:
        return None
    try:
        return tuple(int(value) for value in values[:4])  # type: ignore[return-value]
    except ValueError:
        return None


def _scaled(screen: Screen, bounds: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    """Map measured widget bounds into one panel's 700x420 canvas."""
    x, y, width, height = bounds
    sx = min(max(x, 0), screen.width) / screen.width * CANVAS_W
    sy = min(max(y, 0), screen.height) / screen.height * CANVAS_H
    sw = max(width, 2) / screen.width * CANVAS_W
    sh = max(height, 2) / screen.height * CANVAS_H
    return (
        round(sx, 1),
        round(sy, 1),
        round(min(sw, CANVAS_W - sx), 1),
        round(min(sh, CANVAS_H - sy), 1),
    )


def _schematic_shape(landmark: Landmark, box: tuple[float, float, float, float]) -> str:
    """Draw a recognisable UI shape, not a bare outline rectangle."""
    x, y, width, height = box
    width, height = max(width, 4), max(height, 4)
    kind = landmark.kind
    if kind == "button":
        radius = min(height / 2, 8)
        return (
            f'<rect class="box" x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
            'fill="#dbeafe" stroke="#2563eb" stroke-width="1"/>'
            f'<rect x="{x + 8}" y="{y + height / 2 - 1.5}" width="{max(width - 16, 6):.1f}" '
            'height="3" rx="1.5" fill="#2563eb" fill-opacity="0.55"/>'
        )
    if kind == "chip" and width <= 200:
        radius = height / 2
        return (
            f'<rect class="box" x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius:.1f}" '
            'fill="#dcfce7" stroke="#16a34a" stroke-width="1"/>'
            f'<rect x="{x + 9}" y="{y + height / 2 - 1.5}" width="{max(width - 18, 6):.1f}" '
            'height="3" rx="1.5" fill="#16a34a" fill-opacity="0.55"/>'
        )
    if kind == "card":
        return (
            f'<rect class="box" x="{x}" y="{y}" width="{width}" height="{height}" rx="6" '
            'fill="#f8fafc" stroke="#475569" stroke-width="1.1"/>'
            f'<rect x="{x + 8}" y="{y + 7}" width="{width * 0.42:.1f}" height="4" rx="2" fill="#94a3b8"/>'
            f'<line x1="{x + 6}" y1="{y + 16}" x2="{x + width - 6}" y2="{y + 16}" stroke="#cbd5e1"/>'
            f'<rect x="{x + 8}" y="{y + 23}" width="{width * 0.7:.1f}" height="3" rx="1.5" fill="#cbd5e1"/>'
            f'<rect x="{x + 8}" y="{y + 31}" width="{width * 0.55:.1f}" height="3" rx="1.5" fill="#cbd5e1"/>'
        )
    if kind == "text":
        return (
            f'<rect x="{x}" y="{y + 2}" width="{width * 0.9:.1f}" height="3" rx="1.5" fill="#94a3b8"/>'
            f'<rect x="{x}" y="{y + 9}" width="{width * 0.6:.1f}" height="3" rx="1.5" fill="#cbd5e1"/>'
        )
    # Containers get representative rows so the schematic reads like a page
    # instead of an empty frame.
    rows_out: list[str] = [
        f'<rect class="box" x="{x}" y="{y}" width="{width}" height="{height}" rx="3" '
        'fill="#eef2f7" stroke="#cbd5e1" stroke-width="1"/>'
    ]
    if width >= 80 and height >= 60:
        rows_out.append(
            f'<rect x="{x + 7}" y="{y + 7}" width="{width * 0.38:.1f}" height="4" rx="2" fill="#94a3b8"/>'
        )
        row_height = 12
        count = min(6, max(0, int((height - 24) // row_height)))
        for row in range(count):
            ry = y + 20 + row * row_height
            if ry + 5 > y + height - 4:
                break
            rows_out.append(
                f'<rect x="{x + 7}" y="{ry:.1f}" width="{width * (0.72 if row % 2 else 0.86):.1f}" '
                'height="3" rx="1.5" fill="#cbd5e1"/>'
            )
        if height > 120:
            rows_out.append(
                f'<rect x="{x + width - 6}" y="{y + 18}" width="4" height="{height - 30:.1f}" '
                'rx="2" fill="#94a3b8" fill-opacity="0.5"/>'
            )
    return "".join(rows_out)


def _badge_label(landmark: Landmark) -> str:
    label = f"{landmark.tag} {landmark.name}"
    return label if len(label) <= 18 else label[:17] + "…"


def _badge_width(label: str) -> float:
    return min(max(len(label) * 5.4 + 8, 36), 116)


def _place_badge(
    box: tuple[float, float, float, float],
    label: str,
    placed: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Put a badge beside its widget, avoiding badges already placed."""
    x, y, width, height = box
    badge_w, badge_h = _badge_width(label), 13
    candidates = (
        (x + width + 6, y + height / 2 - badge_h / 2),
        (x - badge_w - 6, y + height / 2 - badge_h / 2),
        (x, y - badge_h - 5),
        (x, y + height + 5),
        (x + width + 6, y + 2),
        (x - badge_w - 6, y + 2),
    )
    best = (0.0, 0.0)
    best_score = float("inf")
    for raw_x, raw_y in candidates:
        cx = min(max(raw_x, 2), CANVAS_W - badge_w - 2)
        cy = min(max(raw_y, 2), CANVAS_H - badge_h - 2)
        overlap = 0.0
        for px, py, pw, ph in placed:
            ox = max(0.0, min(cx + badge_w, px + pw) - max(cx, px))
            oy = max(0.0, min(cy + badge_h, py + ph) - max(cy, py))
            overlap += ox * oy
        score = overlap * 20 + abs(cx - (x + width + 6)) * 0.05
        if score < best_score:
            best_score, best = score, (cx, cy)
    badge = (best[0], best[1], badge_w, badge_h)
    placed.append(badge)
    return badge


def _leader(
    badge: tuple[float, float, float, float], widget: tuple[float, float, float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Shortest line from a badge to the nearest point on its widget."""
    bx, by, bw, bh = badge
    wx, wy, ww, wh = widget
    target_x = min(max(bx + bw / 2, wx), wx + ww)
    target_y = min(max(by + bh / 2, wy), wy + wh)
    source_x = min(max(target_x, bx), bx + bw)
    source_y = min(max(target_y, by), by + bh)
    return (source_x, source_y), (target_x, target_y)


def _render_panel(
    screen: Screen,
    panel_x: int,
    panel_y: int,
    panel_kind: str,
) -> list[str]:
    """Render one captured or schematic panel with badges beside their widgets."""
    title = f"{screen.title} — {panel_kind}"
    lines = [
        f'  <g transform="translate({panel_x} {panel_y})">',
        f'    <rect class="panel" width="{PANEL_W}" height="{PANEL_H}" rx="8" '
        'fill="#f7f8fa" stroke="#d7dae0" stroke-width="1"/>',
        f'    <text x="12" y="22" font-family="{FONT}" font-size="14" font-weight="600" '
        f'fill="#1f2937">{html.escape(title)}</text>',
    ]
    if panel_kind == "captured":
        lines.append(
            f'    <image href="{screen.image}" x="12" y="38" width="{CANVAS_W}" height="{CANVAS_H}" '
            'preserveAspectRatio="xMidYMid meet" stroke="#d7dae0" stroke-width="1"/>'
        )
    else:
        lines.append(
            f'    <rect x="12" y="38" width="{CANVAS_W}" height="{CANVAS_H}" rx="2" '
            'fill="#ffffff" stroke="#d7dae0" stroke-width="1"/>'
        )

    measured = [
        (landmark, _parse_bounds(landmark.bounds))
        for landmark in screen.landmarks
        if not landmark.bounds.startswith("not present")
    ]
    measured = [(landmark, bounds) for landmark, bounds in measured if bounds is not None]

    if panel_kind == "captured":
        for landmark, bounds in measured:
            x, y, width, height = _scaled(screen, bounds)
            # Dashed outline only: a fill stacks across nested widgets and
            # washes the screenshot out.
            lines.append(
                f'    <rect x="{12 + x}" y="{38 + y}" width="{width}" height="{height}" '
                'fill="none" stroke="#b45309" stroke-width="1.1" '
                f'stroke-dasharray="3 2"><title>{html.escape(landmark.tag + " " + landmark.name)}</title></rect>'
            )
    else:
        # Containers first, small controls last: the drawing reads like a UI.
        ordered = sorted(measured, key=lambda item: item[1][2] * item[1][3], reverse=True)
        for landmark, bounds in ordered:
            lines.append("    " + _schematic_shape(landmark, _scaled(screen, bounds)))

    # Badges sit next to the widget they name. A short leader ends in a dot
    # on the exact bounds, so the reference is never ambiguous.
    ordered = sorted(measured, key=lambda item: (item[1][1] + item[1][3] / 2, item[1][0]))
    placed: list[tuple[float, float, float, float]] = []
    for landmark, bounds in ordered:
        widget = _scaled(screen, bounds)
        label = _badge_label(landmark)
        badge = _place_badge(widget, label, placed)
        source, target = _leader(badge, widget)
        tx, ty = 12 + target[0], 38 + target[1]
        sx, sy = 12 + source[0], 38 + source[1]
        bx, by, bw, bh = badge
        lines.append(
            f'    <line x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            'stroke="#b45309" stroke-width="0.9" stroke-opacity="0.85"/>'
        )
        lines.append(
            f'    <circle cx="{tx:.1f}" cy="{ty:.1f}" r="2.4" '
            'fill="#b45309"><title>'
            + html.escape(landmark.tag + " " + landmark.name)
            + "</title></circle>"
        )
        lines.append(
            f'    <rect x="{12 + bx:.1f}" y="{38 + by:.1f}" width="{bw:.1f}" height="{bh}" rx="3" '
            'fill="#fffbeb" fill-opacity="0.95" stroke="#b45309" stroke-width="0.7"/>'
        )
        lines.append(
            f'    <text class="tag" data-tag="{landmark.tag}" data-panel="{panel_kind}" '
            f'x="{12 + bx + 3:.1f}" y="{38 + by + 9.5:.1f}" font-family="{FONT}" font-size="9" '
            f'font-weight="600" fill="#7c2d12">{html.escape(label)}</text>'
        )
    lines.append("  </g>")
    return lines


def render_svg(screens: list[Screen]) -> str:
    """Return the complete side-by-side wireframe SVG as diffable text."""
    height = len(screens) * ROW_H + 8
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {height}" '
        f'width="{VIEW_W}" height="{height}" role="img" '
        'aria-labelledby="wireframe-title">',
        '  <title id="wireframe-title">Numbered UI wireframe of Dataverse Docent</title>',
        "  <!-- Generated by tools/docs/gen_ui_wireframe.py; edit the generator, not this file. -->",
        "  <desc>Each screen appears twice: a full captured view with highlighted widget "
        "bounds on the left, and a clean vector schematic on the right. Numbered badges "
        "in both halves use the same [NN] numbers and point at the exact widget.</desc>",
    ]
    for index, screen in enumerate(screens):
        panel_y = 8 + index * ROW_H
        lines.extend(_render_panel(screen, 8, panel_y, "captured"))
        lines.extend(_render_panel(screen, 752, panel_y, "schematic"))
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

[The wireframe](../assets/ui-wireframe.svg) shows every screen twice: a full captured view on the left and a clean vector schematic on the right. Both halves share the same `[NN]` numbers. A highlight marks the widget's real bounds and a leader line ends in a dot on the widget the badge names, so a label never points at a neighbour. The legend below gives the Qt class, `objectName` (the QSS selector and `findChild` key), layout manager, size policy and measured bounds. For the rules behind the layout, see [UI conventions](../explanation/ui-conventions.md).

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
uv run python tools/docs/gen_ui_wireframe.py --write   # regenerate screenshots, SVG + legend
uv run python tools/docs/gen_ui_wireframe.py --check   # fail if stale
```

The generator boots the app offscreen against a throwaway workspace (never the configured instance), captures each full screen, walks the real widget tree, and writes text-only SVG and Markdown beside the PNGs in `docs/assets/wireframe/`. It assigns tags in registry order, so a published tag keeps its number across runs. `tools/tests/test_ui_wireframe.py` checks that every badge in both halves of the SVG has exactly one legend row, that no number is reused, and that the state and constraint tables are present — without needing Qt.
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
    """Regenerate screenshots and both files; return (svg_changed, doc_changed)."""
    screens = collect()
    svg = render_svg(screens)
    doc = PAGE_TEMPLATE.format(block=render_legend(screens))
    svg_changed = not SVG_PATH.exists() or SVG_PATH.read_text(encoding="utf-8") != svg
    doc_changed = not DOC_PATH.exists() or DOC_PATH.read_text(encoding="utf-8") != doc
    if svg_changed:
        SVG_PATH.write_text(svg, encoding="utf-8", newline="\n")
    if doc_changed:
        DOC_PATH.write_text(doc, encoding="utf-8", newline="\n")
    return svg_changed, doc_changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail when a file is stale")
    group.add_argument("--write", action="store_true", help="regenerate screenshots and both files")
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
