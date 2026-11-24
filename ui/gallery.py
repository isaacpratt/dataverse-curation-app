"""Component gallery: every kit component on one page.

The gallery is the app's visual contract in executable form. It shows
the type scale, the button system, the badge roles, the standard inputs
and the data components - all of them built through the kit, the same
way a view builds them. When the theme changes, the gallery changes
with it; when the kit gains a component, the gallery shows it.

Run it with::

    python main.py --gallery

The gallery is itself a view, so it obeys the same contract as every
other one: it names roles, not palette entries, it builds components,
not raw widgets, and its copy lives in the string catalogue. The
conformance test covers it too.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import t
from ui.theme import (
    ACCENT_PRIMARY,
    ACTIVE_THEME,
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
    transparent_qss,
    transparent_surface_qss,
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
    make_number_field,
    make_page_heading,
    make_plain_text_view,
    make_progress_bar,
    make_search_field,
    make_section_heading,
    make_split_chip,
    make_value_list,
)

__all__ = ["GalleryWindow", "build_gallery"]


# The label tokens the theme defines, in the order they scale down. The
# token is the object name; the note says what the token is for.
_TYPE_SCALE = (
    ("DisplayLG", "22px bold"),
    ("HeadlineLG", "22px semibold"),
    ("HeadlineMD", "17px semibold"),
    ("CardTitle", "15px semibold"),
    ("BodyMD", "13px"),
    ("BodySM", "12px muted"),
    ("HintSM", "12px subtle"),
    ("LabelMD", "11px semibold tracked"),
    ("LabelStrongSM", "11px semibold strong"),
    ("CaptionSM", "11px muted"),
    ("AccentSM", "12px brand"),
    ("SuccessSM", "12px success"),
    ("WarningSM", "12px warning"),
    ("DangerSM", "12px danger"),
)

# The curation labels the theme gives a badge role to. The label text
# drives the role (the theme matches the copy, the way it matches a
# real Dataverse curation label), so the role follows the wording.
_BADGE_SAMPLES = (
    "gallery.badges.draft",
    "gallery.badges.review",
    "gallery.badges.hold",
    "gallery.badges.needs_review",
    "gallery.badges.approve",
    "gallery.badges.publish",
    "gallery.badges.reject",
    "gallery.badges.author_contacted",
    "gallery.badges.deaccessioned",
)

# The role swatches the gallery shows: the catalogue key for the role's
# name and the colour the role stands for.
_ROLE_SWATCHES = (
    ("gallery.roles.page", SURFACE_PAGE),
    ("gallery.roles.card", SURFACE_CARD),
    ("gallery.roles.tint", SURFACE_TINT),
    ("gallery.roles.subtle", SURFACE_SUBTLE),
    ("gallery.roles.raised", SURFACE_RAISED),
    ("gallery.roles.border", BORDER_SUBTLE),
    ("gallery.roles.text", TEXT_PRIMARY),
    ("gallery.roles.muted_text", TEXT_MUTED),
    ("gallery.roles.subtle_text", TEXT_SUBTLE),
    ("gallery.roles.on_tint", TEXT_ON_TINT),
)

# Every button kind, with the catalogue key for its label.
_BUTTON_KINDS = (
    ("primary", "gallery.buttons.primary"),
    ("secondary", "gallery.buttons.secondary"),
    ("ghost", "gallery.buttons.ghost"),
    ("chip", "gallery.buttons.chip"),
    ("cell", "gallery.buttons.cell"),
    ("link", "gallery.buttons.link"),
)

# The sample rows the table shows: the keys for the name and the state,
# and the file count (a number, not copy).
_DATA_ROWS = (
    ("gallery.data.doi_a", "gallery.data.state_review", 42),
    ("gallery.data.doi_b", "gallery.data.state_approved", 7),
    ("gallery.data.doi_c", "gallery.data.state_draft", 0),
)

# The sample rows the tree and the list show.
_DATA_TREE = (
    "gallery.data.tree_repository",
    "gallery.data.tree_one",
    "gallery.data.tree_two",
)

_DATA_LIST = (
    "gallery.data.list_manifest",
    "gallery.data.list_fields",
    "gallery.data.list_extensions",
)


def _swatch(background: str, label: str) -> QWidget:
    """Build a colour swatch for a role - the gallery's palette reference."""
    box = QFrame()
    box.setFixedSize(44, 28)
    box.setStyleSheet(surface_frame_qss(background, TEXT_ON_TINT, radius="6px"))
    box.setToolTip(t("gallery.roles.swatch_tip", name=label, colour=background))
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
        t("gallery.type_scale.title"),
        t("gallery.type_scale.subtitle"),
    )
    for object_name, note in _TYPE_SCALE:
        sample = QLabel(t("gallery.type_scale.sample"))
        sample.setObjectName(object_name)
        sample.setWordWrap(True)
        lay.addWidget(sample)
        lay.addWidget(make_caption_label(note))
    return host


def _button_section() -> QWidget:
    """Every button kind, in every size, plus the disabled state."""
    host, lay = _section(
        t("gallery.buttons.title"),
        t("gallery.buttons.subtitle"),
    )
    for kind, key in _BUTTON_KINDS:
        enabled = make_action_button(t(key), kind=kind)
        disabled = make_action_button(t("gallery.buttons.disabled"), kind=kind)
        disabled.setEnabled(False)
        lay.addLayout(_row(enabled, disabled))
    for size in ("sm", "md", "lg"):
        lay.addLayout(
            _row(
                make_action_button(
                    t("gallery.buttons.size_primary", size=size.upper()),
                    kind="primary",
                    size=size,
                ),
                make_action_button(
                    t("gallery.buttons.size_secondary", size=size.upper()),
                    kind="secondary",
                    size=size,
                ),
                make_action_button(
                    t("gallery.buttons.size_ghost", size=size.upper()),
                    kind="ghost",
                    size=size,
                ),
            )
        )
    return host


def _badge_section() -> QWidget:
    """Show the badge roles, and the badge faces built from explicit roles."""
    host, lay = _section(
        t("gallery.badges.title"),
        t("gallery.badges.subtitle"),
    )
    badges = [make_badge(t(key), label=t(key)) for key in _BADGE_SAMPLES]
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
                t("gallery.badges.pass"),
                background=ACCENT_PRIMARY,
                foreground=SURFACE_CARD,
                border=ACCENT_PRIMARY,
            ),
            make_badge(
                t("gallery.badges.fail"),
                background=STATE_ERROR_BG,
                foreground=STATE_ERROR_TEXT,
                border=STATE_ERROR_TEXT,
            ),
            make_badge(
                t("gallery.badges.live"),
                background=STATE_SUCCESS_GRAPHIC,
                foreground=SURFACE_CARD,
            ),
            make_badge(t("gallery.badges.identifier"), label="identifier", mono=True),
        )
    )
    return host


def _role_section() -> QWidget:
    """Show the role layer: what each colour is FOR."""
    host, lay = _section(
        t("gallery.roles.title"),
        t("gallery.roles.subtitle"),
    )
    grid = QWidget()
    grid_lay = QHBoxLayout(grid)
    grid_lay.setContentsMargins(0, 0, 0, 0)
    grid_lay.setSpacing(10)
    for key, colour in _ROLE_SWATCHES:
        cell = QWidget()
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(0, 0, 0, 0)
        cell_lay.setSpacing(4)
        name = t(key)
        cell_lay.addWidget(_swatch(colour, name))
        cell_lay.addWidget(make_caption_label(name))
        grid_lay.addWidget(cell)
    grid_lay.addStretch(1)
    lay.addWidget(grid)
    return host


def _input_section() -> QWidget:
    """Show the standard inputs."""
    host, lay = _section(
        t("gallery.inputs.title"),
        t("gallery.inputs.subtitle"),
    )
    lay.addWidget(make_field_label(t("gallery.inputs.search_label")))
    lay.addWidget(make_search_field(t("gallery.inputs.search_placeholder")))
    lay.addWidget(make_field_label(t("gallery.inputs.single_line_label")))
    lay.addWidget(make_line_edit(t("gallery.inputs.single_line_placeholder")))
    lay.addWidget(make_field_label(t("gallery.inputs.dropdown_label")))
    lay.addWidget(
        make_combo(
            [
                (t("gallery.inputs.dropdown_placeholder"), ""),
                (t("gallery.inputs.dropdown_required"), "required"),
                (t("gallery.inputs.dropdown_optional"), "optional"),
            ]
        )
    )
    lay.addWidget(make_field_label(t("gallery.inputs.multi_line_label")))
    lay.addWidget(make_multiline_input(t("gallery.inputs.multi_line_placeholder"), height=96))
    lay.addWidget(make_field_label(t("gallery.inputs.read_only_label")))
    lay.addWidget(make_plain_text_view(t("gallery.inputs.read_only_content")))
    lay.addWidget(make_field_label(t("gallery.inputs.check_box_label")))
    lay.addWidget(make_checkbox(t("gallery.inputs.check_box_checked"), checked=True))
    lay.addWidget(make_checkbox(t("gallery.inputs.check_box_unchecked")))
    disabled_box = make_checkbox(t("gallery.inputs.check_box_disabled"))
    disabled_box.setEnabled(False)
    lay.addWidget(disabled_box)
    disabled_checked = make_checkbox(t("gallery.inputs.check_box_disabled_checked"), checked=True)
    disabled_checked.setEnabled(False)
    lay.addWidget(disabled_checked)
    lay.addWidget(make_field_label(t("gallery.inputs.number_label")))
    lay.addWidget(
        make_number_field(50, minimum=0, maximum=10000, tip=t("gallery.inputs.number_tip"))
    )
    lay.addWidget(make_field_label(t("gallery.inputs.number_bound_label")))
    lay.addWidget(make_number_field(10000, minimum=0, maximum=10000))
    lay.addWidget(make_field_label(t("gallery.inputs.number_disabled_label")))
    disabled_num = make_number_field(3, minimum=0, maximum=10000)
    disabled_num.setEnabled(False)
    lay.addWidget(disabled_num)
    lay.addWidget(make_field_label(t("gallery.inputs.value_list_label")))
    lay.addWidget(
        make_value_list(
            [t("gallery.inputs.value_list_a"), t("gallery.inputs.value_list_b")],
            placeholder=t("gallery.inputs.value_list_placeholder"),
            add_tip=t("common.add_tip"),
        )
    )
    lay.addWidget(make_field_label(t("gallery.inputs.value_list_empty_label")))
    lay.addWidget(
        make_value_list(
            [],
            placeholder=t("gallery.inputs.value_list_placeholder"),
            add_tip=t("common.add_tip"),
            empty_text=t("gallery.inputs.value_list_empty"),
        )
    )
    lay.addWidget(make_field_label(t("gallery.inputs.progress_label")))
    bar = make_progress_bar()
    bar.setRange(0, 100)
    bar.setValue(60)
    lay.addWidget(bar)
    lay.addWidget(make_field_label(t("gallery.inputs.progress_ring_label")))
    from ui.widgets import RingProgress

    ring = RingProgress(diameter=28)
    ring.setFraction(0.6)
    lay.addWidget(ring)
    return host


def _container_section() -> QWidget:
    """Show the container components: cards, chips, metric tiles."""
    host, lay = _section(
        t("gallery.containers.title"),
        t("gallery.containers.subtitle"),
    )
    card, body, _title, header = make_card(t("gallery.containers.card_title"))
    body.addWidget(make_body_label(t("gallery.containers.card_body")))
    header.addWidget(
        make_action_button(t("gallery.containers.card_action"), kind="ghost", size="sm")
    )
    lay.addWidget(card)

    lay.addLayout(
        _row(
            make_split_chip(t("gallery.containers.chip_a"), active=True),
            make_split_chip(t("gallery.containers.chip_b")),
        )
    )

    tile = QFrame()
    tile.setStyleSheet(surface_frame_qss(SURFACE_CARD, SURFACE_TINT))
    tile_lay = QVBoxLayout(tile)
    tile_lay.setContentsMargins(16, 12, 16, 12)
    tile_lay.setSpacing(2)
    tile_lay.addWidget(make_field_label(t("gallery.containers.metric_label")))
    tile_lay.addWidget(make_metric_value("12"))
    lay.addWidget(tile)
    return host


def _icons_section() -> QWidget:
    """Show every bundled glyph, so a missing or ugly mark is visible here."""
    from ui.icons import ICON_ROLES, icon

    host, lay = _section(
        t("gallery.icons.title"),
        t("gallery.icons.subtitle"),
    )
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(10)
    names = sorted({*ICON_ROLES.values()})
    columns = 8
    for index, name in enumerate(names):
        row, col = divmod(index, columns)
        cell = QWidget()
        cell.setObjectName("IconTile")
        cell.setStyleSheet(transparent_surface_qss("IconTile"))
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(0, 0, 0, 0)
        cell_lay.setSpacing(2)
        marks = QHBoxLayout()
        marks.setContentsMargins(0, 0, 0, 0)
        marks.setSpacing(6)
        for size in (16, 20):
            mark = QLabel()
            mark.setPixmap(icon(name, color=TEXT_PRIMARY, size=size).pixmap(QSize(size, size)))
            mark.setFixedSize(size + 2, size + 2)
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mark.setStyleSheet(transparent_qss("QLabel"))
            mark.setProperty("icon_name", name)
            mark.setProperty("icon_size", size)
            mark.setToolTip(t("gallery.icons.mark_tip", name=name, size=size))
            marks.addWidget(mark)
        marks.addStretch(1)
        cell_lay.addLayout(marks)
        caption = QLabel(name)
        caption.setObjectName("CaptionSM")
        caption.setProperty("glyph_caption", name)
        cell_lay.addWidget(caption)
        grid.addWidget(cell, row, col)
    grid.setColumnStretch(columns, 1)
    lay.addLayout(grid)
    roles = ", ".join(f"{role} → {glyph}" for role, glyph in sorted(ICON_ROLES.items()))
    note = QLabel(t("gallery.icons.roles", roles=roles))
    note.setObjectName("CaptionSM")
    note.setWordWrap(True)
    lay.addWidget(note)
    return host


def _data_section() -> QWidget:
    """Show the data components: table, tree and list."""
    host, lay = _section(
        t("gallery.data.title"),
        t("gallery.data.subtitle"),
    )

    table = AppTable(
        [
            t("gallery.data.column_dataset"),
            t("gallery.data.column_state"),
            t("gallery.data.column_files"),
        ],
        widths={0: 220, 1: 140, 2: 80},
    )
    for name_key, state_key, files in _DATA_ROWS:
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, _table_item(t(name_key)))
        table.setItem(row, 1, _table_item(t(state_key)))
        table.setItem(row, 2, _table_item(str(files)))
    lay.addWidget(table)

    tree = AppTreeWidget(flush=False)
    for key in _DATA_TREE:
        item = _tree_item(t(key))
        tree.addTopLevelItem(item)
    lay.addWidget(tree)

    lst = make_list()
    for key in _DATA_LIST:
        lst.addItem(t(key))
    lay.addWidget(lst)
    return host


def _table_item(text: str) -> QTableWidgetItem:
    """Build a table cell (the table owns the item, the gallery owns the text)."""
    return QTableWidgetItem(text)


def _tree_item(label: str) -> QTreeWidgetItem:
    """Build a tree item (the tree owns the item, the gallery owns the text)."""
    return QTreeWidgetItem([label])


class GalleryWindow(QWidget):
    """The gallery window: the kit, one page."""

    def __init__(self, parent: QWidget | None = None, config: Any = None) -> None:
        super().__init__(parent)
        self._config = config
        # The layout the sections are built into; set by _build_gallery so
        # the selector handler can rebuild in place.
        self._body: QVBoxLayout | None = None
        self.setWindowTitle(t("gallery.window_title"))
        self.resize(960, 900)
        self.setObjectName("GalleryWindow")
        self.setStyleSheet(page_background_qss("GalleryWindow"))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # Title row with theme selector
        title_row = QHBoxLayout()
        title_row.setSpacing(16)
        title, subtitle = make_page_heading(
            t("gallery.heading"),
            t("gallery.subheading"),
        )
        title_row.addWidget(title)
        if subtitle is not None:
            title_row.addWidget(subtitle)
        title_row.addStretch(1)

        # Theme selector — opens on the curator's saved view (dv-4jm.6).
        # The combo carries the English label as its item text and the
        # mode as item data, so the selection is read back by data.
        self._theme_selector = make_combo(
            [
                (t("gallery.theme.light"), "light"),
                (t("gallery.theme.dark"), "dark"),
                (t("gallery.theme.both"), "both"),
            ],
            min_width=180,
        )
        self._gallery_mode = self._saved_gallery_mode()
        self._select_gallery_mode(self._gallery_mode)
        self._theme_selector.currentIndexChanged.connect(self._on_theme_changed)
        self._theme_selector.setToolTip(t("gallery.theme.tip"))
        title_row.addWidget(self._theme_selector)
        outer.addLayout(title_row)

        if subtitle is not None:
            outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("GalleryContent")
        content.setStyleSheet(page_background_qss("GalleryContent"))
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(24)

        # Build the saved view: "both" shows the two themes side by side,
        # a single theme shows just that one.
        self._build_gallery(body)

        body.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        footer = QLabel(t("gallery.footer"))
        footer.setObjectName("CaptionSM")
        footer.setWordWrap(True)
        footer.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(footer)
        footer.setToolTip(t("gallery.footer_tip", colour=TEXT_MUTED))

    def _saved_gallery_mode(self) -> str:
        """Return the gallery view the config remembers ("light"/"dark"/"both")."""
        mode = ""
        if self._config is not None:
            try:
                mode = str(getattr(self._config.app, "gallery_theme_mode", "") or "")
            except Exception:
                mode = ""
        return mode if mode in ("light", "dark", "both") else "both"

    def _select_gallery_mode(self, mode: str) -> None:
        """Point the combo at ``mode`` without firing the change handler."""
        index = self._theme_selector.findData(mode)
        if index >= 0:
            self._theme_selector.blockSignals(True)
            self._theme_selector.setCurrentIndex(index)
            self._theme_selector.blockSignals(False)

    def _remember_gallery_mode(self, mode: str) -> None:
        """Persist the chosen view so the next open starts there (dv-4jm.6)."""
        if self._config is None:
            return
        self._config.app.gallery_theme_mode = mode
        try:
            self._config.save()
        except Exception as exc:
            # A read-only or unwritable config must not stop the curator
            # switching views; say so in the log rather than silently
            # pretending the choice was kept.
            try:
                from curation.applog import get_app_log

                get_app_log().warn(f"gallery: could not persist theme view {mode!r}: {exc}")
            except Exception:
                pass

    def _on_theme_changed(self, _index: int = 0) -> None:
        """Rebuild the page for the selected view and remember it.

        Connected to ``currentIndexChanged``, so the argument is the new
        row index; the mode itself is read from the combo's item data.
        """
        mode = self._theme_selector.currentData() or "both"
        self._gallery_mode = str(mode)
        self._remember_gallery_mode(self._gallery_mode)
        body = self._body
        if body is None:
            return
        # Drop the old sections; the layout keeps its trailing stretch.
        while body.count():
            item = body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._build_gallery(body)
        body.addStretch(1)

    def _build_gallery(self, body: QVBoxLayout) -> None:
        """Fill ``body`` with the sections for the current view mode."""
        self._body = body
        if self._gallery_mode == "both":
            self._show_dual_theme(body)
        else:
            body.addWidget(self._single_theme(self._gallery_mode))

    def _sections(self) -> tuple[Any, ...]:
        """Return the kit sections, in page order."""
        return (
            _type_scale_section(),
            _role_section(),
            _button_section(),
            _badge_section(),
            _input_section(),
            _container_section(),
            _icons_section(),
            _data_section(),
        )

    def _single_theme(self, theme_name: str) -> QWidget:
        """One theme's sections in a scrolling column."""
        from PySide6.QtWidgets import QApplication

        from ui.theme import apply_theme, set_active_theme

        host = QWidget()
        host.setObjectName("GalleryContentSingle")
        host.setStyleSheet(page_background_qss("GalleryContentSingle", theme=theme_name))
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(24)

        # Build the sections against the requested palette, then put the
        # app back on the curator's own theme.
        previous = ACTIVE_THEME
        set_active_theme(theme_name)
        app_instance = QApplication.instance()
        if isinstance(app_instance, QApplication):
            apply_theme(app_instance, theme_name, retheme=False)
        try:
            for section in self._sections():
                lay.addWidget(section)
        finally:
            set_active_theme(previous)
            if isinstance(app_instance, QApplication):
                apply_theme(app_instance, previous, retheme=False)
        return host

    def _show_dual_theme(self, body: QVBoxLayout) -> None:
        """Show light and dark themes side by side for each section."""
        from PySide6.QtWidgets import QApplication

        from ui.theme import apply_theme, set_active_theme

        # The curator's own theme, restored once both columns are built.
        previous = ACTIVE_THEME

        # Build light theme sections
        light_content = QWidget()
        light_content.setObjectName("GalleryContentLight")
        light_content.setStyleSheet(page_background_qss("GalleryContentLight", theme="light"))
        light_body = QVBoxLayout(light_content)
        light_body.setContentsMargins(0, 0, 0, 0)
        light_body.setSpacing(24)

        # Build dark theme sections
        dark_content = QWidget()
        dark_content.setObjectName("GalleryContentDark")
        dark_content.setStyleSheet(page_background_qss("GalleryContentDark", theme="dark"))
        dark_body = QVBoxLayout(dark_content)
        dark_body.setContentsMargins(0, 0, 0, 0)
        dark_body.setSpacing(24)

        # Apply light theme temporarily to build light sections
        set_active_theme("light")
        app_instance = QApplication.instance()
        assert isinstance(app_instance, QApplication)
        apply_theme(app_instance, "light", retheme=False)

        # Add sections to light body
        for section in self._sections():
            light_body.addWidget(section)

        # Apply dark theme temporarily to build dark sections
        set_active_theme("dark")
        app_instance = QApplication.instance()
        assert isinstance(app_instance, QApplication)
        apply_theme(app_instance, "dark", retheme=False)

        # Add sections to dark body
        for section in self._sections():
            dark_body.addWidget(section)

        # Restore the curator's theme for the actual app
        set_active_theme(previous)
        app_instance = QApplication.instance()
        assert isinstance(app_instance, QApplication)
        apply_theme(app_instance, previous, retheme=False)

        # Create side-by-side layout
        dual_host = QWidget()
        dual_host.setObjectName("GalleryDualTheme")
        dual_layout = QHBoxLayout(dual_host)
        dual_layout.setContentsMargins(0, 0, 0, 0)
        dual_layout.setSpacing(16)

        # Light column
        light_col = QWidget()
        light_col.setObjectName("GalleryThemeColumn")
        light_col_lay = QVBoxLayout(light_col)
        light_col_lay.setContentsMargins(8, 8, 8, 8)
        light_col_lay.setSpacing(16)

        # Light theme label
        light_label = QLabel(t("gallery.theme.light"))
        light_label.setObjectName("LabelStrongSM")
        light_col_lay.addWidget(light_label)

        light_scroll = QScrollArea()
        light_scroll.setWidgetResizable(True)
        light_scroll.setFrameShape(QFrame.Shape.NoFrame)
        light_scroll.setWidget(light_content)
        light_col_lay.addWidget(light_scroll, 1)

        # Dark column
        dark_col = QWidget()
        dark_col.setObjectName("GalleryThemeColumn")
        dark_col_lay = QVBoxLayout(dark_col)
        dark_col_lay.setContentsMargins(8, 8, 8, 8)
        dark_col_lay.setSpacing(16)

        # Dark theme label
        dark_label = QLabel(t("gallery.theme.dark"))
        dark_label.setObjectName("LabelStrongSM")
        dark_col_lay.addWidget(dark_label)

        dark_scroll = QScrollArea()
        dark_scroll.setWidgetResizable(True)
        dark_scroll.setFrameShape(QFrame.Shape.NoFrame)
        dark_scroll.setWidget(dark_content)
        dark_col_lay.addWidget(dark_scroll, 1)

        dual_layout.addWidget(light_col, 1)
        dual_layout.addWidget(dark_col, 1)

        body.addWidget(dual_host)


def build_gallery(parent: QWidget | None = None, config: Any = None) -> GalleryWindow:
    """Build the gallery window.

    ``config`` is the app config: the gallery reads and writes the
    curator's chosen view in ``app.gallery_theme_mode`` (dv-4jm.6).
    """
    return GalleryWindow(parent, config)


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
