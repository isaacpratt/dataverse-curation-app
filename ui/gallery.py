"""Component gallery: every kit component on one page.

The gallery is the app's visual contract in executable form. It shows
the type scale, the button system, the badge roles, the standard inputs
and the data components - all of them built through the kit, the same
way a view builds them. When the theme changes, the gallery changes
with it; when the kit gains a component, the gallery shows it.

Run it with::

    python main.py --gallery

The gallery is itself a view, so it obeys the same contract as every
other one: it names roles, not palette entries, and it builds
components, not raw widgets. The conformance test covers it too.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    ACCENT_PRIMARY,
    BORDER_SUBTLE,
    STATE_ERROR_BG,
    STATE_ERROR_TEXT,
    STATE_SUCCESS_GRAPHIC,
    SURFACE_CARD,
    SURFACE_PAGE,
    SURFACE_RAISED,
    SURFACE_SUBTLE,
    SURFACE_TINT,
    TEXT_MUTED,
    TEXT_ON_TINT,
    TEXT_PRIMARY,
    TEXT_SUBTLE,
    page_background_qss,
    surface_frame_qss,
)
from ui.widgets import (
    AppTable,
    AppTreeWidget,
    make_action_button,
    make_badge,
    make_body_label,
    make_caption_label,
    make_card,
    make_checkbox,
    make_combo,
    make_field_label,
    make_line_edit,
    make_list,
    make_metric_value,
    make_multiline_input,
    make_page_heading,
    make_plain_text_view,
    make_progress_bar,
    make_search_field,
    make_section_heading,
    make_split_chip,
)

__all__ = ["GalleryWindow", "build_gallery"]


# The label tokens the theme defines, in the order they scale down.
_TYPE_SCALE = (
    ("DisplayLG", "DisplayLG", "22px bold"),
    ("HeadlineLG", "HeadlineLG", "22px semibold"),
    ("HeadlineMD", "HeadlineMD", "17px semibold"),
    ("CardTitle", "CardTitle", "15px semibold"),
    ("BodyMD", "BodyMD", "13px"),
    ("BodySM", "BodySM", "12px muted"),
    ("HintSM", "HintSM", "12px subtle"),
    ("LabelMD", "LabelMD", "11px semibold tracked"),
    ("LabelStrongSM", "LabelStrongSM", "11px semibold strong"),
    ("CaptionSM", "CaptionSM", "11px muted"),
    ("AccentSM", "AccentSM", "12px brand"),
    ("SuccessSM", "SuccessSM", "12px success"),
    ("WarningSM", "WarningSM", "12px warning"),
    ("DangerSM", "DangerSM", "12px danger"),
)

# The badge roles the theme ships, with a sample label for each.
_BADGE_SAMPLES = (
    ("Draft", "draft"),
    ("In Review", "review"),
    ("Hold", "hold"),
    ("Needs Review", "needs review"),
    ("Approved", "approve"),
    ("Published", "publish"),
    ("Rejected", "reject"),
    ("Author Contacted", "author contacted"),
    ("Deaccessioned", "deaccessioned"),
)


def _swatch(background: str, label: str) -> QWidget:
    """Build a colour swatch for a role - the gallery's palette reference."""
    box = QFrame()
    box.setFixedSize(44, 28)
    box.setStyleSheet(surface_frame_qss(background, TEXT_ON_TINT, radius="6px"))
    box.setToolTip(f"{label}: {background}")
    return box


def _section(title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
    """Build one gallery section (a heading plus a body layout)."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(make_section_heading(title))
    if subtitle:
        lay.addWidget(make_caption_label(subtitle))
    return host, lay


def _row(*widgets: QWidget, spacing: int = 8) -> QHBoxLayout:
    """Build a horizontal run of components."""
    row = QHBoxLayout()
    row.setSpacing(spacing)
    row.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        row.addWidget(widget)
    row.addStretch(1)
    return row


def _type_scale_section() -> QWidget:
    """Every label token the theme defines."""
    host, lay = _section(
        "Type scale",
        "One size per role: the theme owns the type scale, a view names the role.",
    )
    for object_name, _label, note in _TYPE_SCALE:
        sample = QLabel("The quick brown fox jumps over the lazy dog")
        sample.setObjectName(object_name)
        sample.setWordWrap(True)
        lay.addWidget(sample)
        lay.addWidget(make_caption_label(note))
    return host


def _button_section() -> QWidget:
    """Every button kind, in every size, plus the disabled state."""
    host, lay = _section(
        "Buttons",
        "One system: the app-level rules and the scoped copies come from one generator.",
    )
    for kind in ("primary", "secondary", "ghost", "chip", "cell", "link"):
        enabled = make_action_button(f"{kind.title()}", kind=kind)
        disabled = make_action_button("Disabled", kind=kind)
        disabled.setEnabled(False)
        lay.addLayout(_row(enabled, disabled))
    for size in ("sm", "md", "lg"):
        lay.addLayout(
            _row(
                make_action_button(f"{size.upper()} primary", kind="primary", size=size),
                make_action_button(f"{size.upper()} secondary", kind="secondary", size=size),
                make_action_button(f"{size.upper()} ghost", kind="ghost", size=size),
            )
        )
    return host


def _badge_section() -> QWidget:
    """Show the badge roles, and the badge faces built from explicit roles."""
    host, lay = _section(
        "Badges",
        "A status label picks a role; the fill and the text are checked for contrast.",
    )
    badges = [make_badge(label, label=key) for label, key in _BADGE_SAMPLES]
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for badge in badges:
        row.addWidget(badge)
    row.addStretch(1)
    lay.addWidget(wrap)
    lay.addLayout(
        _row(
            make_badge(
                "PASS",
                background=ACCENT_PRIMARY,
                foreground=SURFACE_CARD,
                border=ACCENT_PRIMARY,
            ),
            make_badge(
                "FAIL",
                background=STATE_ERROR_BG,
                foreground=STATE_ERROR_TEXT,
                border=STATE_ERROR_TEXT,
            ),
            make_badge("LIVE", background=STATE_SUCCESS_GRAPHIC, foreground=SURFACE_CARD),
            make_badge("doi:10.5072/FK2/ABC123", label="identifier", mono=True),
        )
    )
    return host


def _role_section() -> QWidget:
    """Show the role layer: what each colour is FOR."""
    host, lay = _section(
        "Roles",
        "The palette says what a colour is; a role says what it is for.",
    )
    rows = (
        ("Page", SURFACE_PAGE),
        ("Card", SURFACE_CARD),
        ("Tint", SURFACE_TINT),
        ("Subtle", SURFACE_SUBTLE),
        ("Raised", SURFACE_RAISED),
        ("Border", BORDER_SUBTLE),
        ("Text", TEXT_PRIMARY),
        ("Muted text", TEXT_MUTED),
        ("Subtle text", TEXT_SUBTLE),
        ("On tint", TEXT_ON_TINT),
    )
    grid = QWidget()
    grid_lay = QHBoxLayout(grid)
    grid_lay.setContentsMargins(0, 0, 0, 0)
    grid_lay.setSpacing(10)
    for name, colour in rows:
        cell = QWidget()
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(0, 0, 0, 0)
        cell_lay.setSpacing(4)
        cell_lay.addWidget(_swatch(colour, name))
        cell_lay.addWidget(make_caption_label(name))
        grid_lay.addWidget(cell)
    grid_lay.addStretch(1)
    lay.addWidget(grid)
    return host


def _input_section() -> QWidget:
    """Show the standard inputs."""
    host, lay = _section(
        "Inputs",
        "One field shape: the same height, focus ring and radius everywhere.",
    )
    lay.addWidget(make_field_label("Search"))
    lay.addWidget(make_search_field("Search the queue"))
    lay.addWidget(make_field_label("Single line"))
    lay.addWidget(make_line_edit("A single-line field"))
    lay.addWidget(make_field_label("Dropdown"))
    lay.addWidget(
        make_combo(
            [
                ("Select a level", ""),
                ("Required", "required"),
                ("Optional", "optional"),
            ]
        )
    )
    lay.addWidget(make_field_label("Multi-line"))
    lay.addWidget(make_multiline_input("Write a note", height=96))
    lay.addWidget(make_field_label("Read-only"))
    lay.addWidget(make_plain_text_view("A read-only plain-text view"))
    lay.addWidget(make_field_label("Check box"))
    lay.addWidget(make_checkbox("Include the guestbook response", checked=True))
    lay.addWidget(make_checkbox("A disabled option"))
    lay.addWidget(make_field_label("Progress"))
    bar = make_progress_bar()
    bar.setRange(0, 100)
    bar.setValue(60)
    lay.addWidget(bar)
    return host


def _container_section() -> QWidget:
    """Show the container components: cards, chips, metric tiles."""
    host, lay = _section("Containers", "Cards, chips and the metric tile.")
    card, body, _title, header = make_card("Card")
    body.addWidget(make_body_label("A card holds a title, a body and a header row."))
    header.addWidget(make_action_button("Action", kind="ghost", size="sm"))
    lay.addWidget(card)

    lay.addLayout(
        _row(
            make_split_chip("doi:10.5072/FK2/ABC123", active=True),
            make_split_chip("doi:10.5072/FK2/XYZ789"),
        )
    )

    tile = QFrame()
    tile.setStyleSheet(surface_frame_qss(SURFACE_CARD, SURFACE_TINT))
    tile_lay = QVBoxLayout(tile)
    tile_lay.setContentsMargins(16, 12, 16, 12)
    tile_lay.setSpacing(2)
    tile_lay.addWidget(make_field_label("DATASETS"))
    tile_lay.addWidget(make_metric_value("12"))
    lay.addWidget(tile)
    return host


def _data_section() -> QWidget:
    """Show the data components: table, tree and list."""
    host, lay = _section("Data", "Tables, trees and lists share one header and one lane.")

    table = AppTable(["Dataset", "State", "Files"], widths={0: 220, 1: 140, 2: 80})
    for name, state, files in (
        ("doi:10.5072/FK2/ABC123", "In Review", "42"),
        ("doi:10.5072/FK2/XYZ789", "Approved", "7"),
        ("doi:10.5072/FK2/AAA000", "Draft", "0"),
    ):
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, _table_item(name))
        table.setItem(row, 1, _table_item(state))
        table.setItem(row, 2, _table_item(files))
    lay.addWidget(table)

    tree = AppTreeWidget(flush=False)
    for label in ("Repository", "Dataset one", "Dataset two"):
        item = _tree_item(label)
        tree.addTopLevelItem(item)
    lay.addWidget(tree)

    lst = make_list()
    for text in ("File manifest", "Metadata fields", "Extensions"):
        lst.addItem(text)
    lay.addWidget(lst)
    return host


def _table_item(text: str):
    """Build a table cell (the table owns the item, the gallery owns the text)."""
    from PySide6.QtWidgets import QTableWidgetItem

    return QTableWidgetItem(text)


def _tree_item(label: str):
    """Build a tree item (the tree owns the item, the gallery owns the text)."""
    from PySide6.QtWidgets import QTreeWidgetItem

    return QTreeWidgetItem([label])


class GalleryWindow(QWidget):
    """The gallery window: the kit, one page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dataverse Docent - component gallery")
        self.resize(960, 900)
        self.setObjectName("GalleryWindow")
        self.setStyleSheet(page_background_qss("GalleryWindow"))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title, subtitle = make_page_heading(
            "Component gallery",
            "Every component the app ships, built through the kit.",
        )
        outer.addWidget(title)
        if subtitle is not None:
            outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("GalleryContent")
        content.setStyleSheet(page_background_qss("GalleryContent"))
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(24)
        for section in (
            _type_scale_section(),
            _role_section(),
            _button_section(),
            _badge_section(),
            _input_section(),
            _container_section(),
            _data_section(),
        ):
            body.addWidget(section)
        body.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        footer = QLabel(
            "Text colours come from the theme's roles; the contrast contract "
            "is checked by ui/tests/test_contrast.py."
        )
        footer.setObjectName("CaptionSM")
        footer.setWordWrap(True)
        footer.setTextFormat(Qt.PlainText)
        outer.addWidget(footer)
        footer.setToolTip(f"Muted text role: {TEXT_MUTED}")


def build_gallery(parent: QWidget | None = None) -> GalleryWindow:
    """Build the gallery window."""
    return GalleryWindow(parent)


def main() -> int:
    """Run the gallery on its own (``python -m ui.gallery``)."""
    import sys

    from PySide6.QtWidgets import QApplication

    from ui.theme import apply_theme

    app = QApplication(sys.argv)
    apply_theme(app)
    window = build_gallery()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
