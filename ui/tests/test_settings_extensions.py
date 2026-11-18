"""Settings → Extensions: icon-only Installed cells and the Version column (dv-bld).

The Installed column shows only a check (present) or an X (absent) with the
words in the tooltip; the Version column shows the installed version of
detected packages.
"""

import json

import pytest


@pytest.fixture
def pane(qapp, tmp_path, monkeypatch):
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    monkeypatch.setattr(SettingsPane, "_start_size_worker", lambda self: None)

    import builtins
    import importlib.metadata

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "h5py":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    def fake_version(name):
        if name == "pyreadstat":
            return "1.2.3"
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    # Both external tools report "not found".
    monkeypatch.setattr(SettingsPane, "_detect_tool", staticmethod(lambda key, configured: ""))

    cfg = Config()
    cfg.dataverse.base_url = "https://demo.borealisdata.ca"
    cfg.dataverse.api_token = ""
    cfg.dataverse.collection = "dv"
    cfg.app.workspace = tmp_path
    cfg.app.tesseract = ""
    cfg.app.exiftool = ""
    widget = SettingsPane(cfg)
    yield widget
    widget.deleteLater()


def _row(pane, package):
    for row in range(pane.ext_table.rowCount()):
        item = pane.ext_table.item(row, 0)
        if item is not None and item.text() == package:
            return row
    raise AssertionError(f"row for {package!r} not found")


def test_version_column_and_icon_only_installed_cells(pane):
    # pyreadstat: installed (metadata reports 1.2.3) — check icon, Version 1.2.3.
    row = _row(pane, "pyreadstat")
    inst = pane.ext_table.item(row, 1)
    assert inst is not None
    assert inst.text() == "", "Installed column is icon-only"
    assert not inst.icon().isNull(), "installed rows carry an icon"
    assert inst.toolTip(), "state must not be colour-only: tooltip carries the words"
    assert pane.ext_table.item(row, 2).text() == "1.2.3"

    # h5py: neither metadata nor import — X icon, Version —.
    row = _row(pane, "h5py")
    inst = pane.ext_table.item(row, 1)
    assert inst is not None
    assert inst.text() == ""
    assert not inst.icon().isNull()
    assert inst.toolTip() == "Not installed"
    assert pane.ext_table.item(row, 2).text() == "—"


def test_installed_but_unversioned_package_reads_dash(pane):
    # chardet imports fine but metadata is faked away: installed (check) with — version.
    row = _row(pane, "chardet")
    inst = pane.ext_table.item(row, 1)
    assert inst is not None
    assert inst.text() == ""
    assert not inst.icon().isNull()
    assert inst.toolTip() == "installed"
    assert pane.ext_table.item(row, 2).text() == "—"


def test_tools_rows_show_x_and_dash_version(pane):
    from ui.settings_dialog import SettingsPane

    base = len(SettingsPane.EXTENSIONS)
    for offset in range(len(SettingsPane.TOOLS)):
        row = base + offset
        inst = pane.ext_table.item(row, 1)
        assert inst is not None
        assert inst.text() == "", "tools rows are icon-only too"
        assert not inst.icon().isNull()
        assert pane.ext_table.item(row, 2).text() == "—"


def test_reordered_saved_layout_is_remapped_onto_new_shape(qapp, tmp_path, monkeypatch):
    from curation.config import Config
    from ui.settings_dialog import SettingsPane

    # A layout saved before the Version column: five widths for
    # [Package, Installed, Size, Used for, Action].
    legacy = {"v": 1, "widths": [100, 80, 70, 150, 260], "order": [0, 1, 2, 3, 4]}
    (tmp_path / "table_layout.json").write_text(
        json.dumps({"extensions": legacy}), encoding="utf-8"
    )

    monkeypatch.setattr(SettingsPane, "_start_size_worker", lambda self: None)
    monkeypatch.setattr(SettingsPane, "_detect_tool", staticmethod(lambda key, configured: ""))
    import importlib.metadata

    monkeypatch.setattr(
        importlib.metadata,
        "version",
        lambda name: (_ for _ in ()).throw(importlib.metadata.PackageNotFoundError(name)),
    )
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        # Only the extension import probes may fail; pytest itself imports freely.
        if name in {
            "pyreadstat",
            "netCDF4",
            "h5py",
            "tifffile",
            "PIL",
            "pypdf",
            "lxml",
            "openpyxl",
            "chardet",
            "piigex",
            "hush",
        }:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    cfg = Config()
    cfg.dataverse.base_url = "https://demo.borealisdata.ca"
    cfg.dataverse.api_token = ""
    cfg.dataverse.collection = "dv"
    cfg.app.workspace = tmp_path
    cfg.app.tesseract = ""
    cfg.app.exiftool = ""
    widget = SettingsPane(cfg)
    try:
        header = widget.ext_table.horizontalHeader()
        # Columns 0-3 and 5 honour the migrated widths. Column 4 (Used for)
        # is the Stretch section — its width is viewport-dependent, not saved.
        assert [header.sectionSize(i) for i in (0, 1, 2, 3, 5)] == [100, 80, 90, 70, 260]
    finally:
        widget.deleteLater()


def test_extensions_header_has_version_column(pane):
    headers = [
        pane.ext_table.horizontalHeaderItem(i).text() for i in range(pane.ext_table.columnCount())
    ]
    assert headers == ["Package", "Installed", "Version", "Size", "Used for", "Action"]
