"""In-app file preview (dv-koz): pure readers + the sidebar card."""

import pytest

from ui import preview


class TestCsvPreview:
    def test_csv_first_rows_and_types(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age,score\nAnn,30,1.5\nBob,40,2.5\n", encoding="utf-8")
        result = preview.preview_file(f)
        assert result["kind"] == "tabular"
        assert result["columns"] == ["name", "age", "score"]
        assert result["types"] == ["text", "integer", "numeric"]
        assert result["rows"][0] == ["Ann", "30", "1.5"]
        assert result["encoding"].startswith("utf-8")

    def test_tsv_delimiter(self, tmp_path):
        f = tmp_path / "data.tsv"
        f.write_text("a\tb\n1\t2\n", encoding="utf-8")
        result = preview.preview_file(f)
        assert result["columns"] == ["a", "b"]

    def test_invalid_csv_headers_fall_back(self, tmp_path):
        f = tmp_path / "broken.csv"
        f.write_text("unclosed-\"quote\nrow2\n", encoding="utf-8")
        result = preview.preview_file(f)
        assert result["kind"] == "tabular"  # parse error degrades, never raises


class TestTextAndJson:
    def test_text_head_and_encoding_fallback(self, tmp_path):
        f = tmp_path / "legacy.txt"
        f.write_bytes("café".encode("latin-1") + b"\nrest\n")
        result = preview.preview_file(f)
        assert result["kind"] == "text"
        assert result["encoding"] == "latin-1"
        assert "café" in result["text"]

    def test_text_truncated_to_40_lines(self, tmp_path):
        f = tmp_path / "long.txt"
        f.write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
        result = preview.preview_file(f)
        assert len(result["lines"]) == 40
        assert result["truncated"] is True

    def test_json_pretty_prints(self, tmp_path):
        f = tmp_path / "x.json"
        f.write_text('{"a": [1, 2]}', encoding="utf-8")
        result = preview.preview_file(f)
        assert result["kind"] == "json"
        assert '"a"' in result["text"]

    def test_json_invalid_shows_raw(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not json", encoding="utf-8")
        result = preview.preview_file(f)
        assert result["kind"] == "json"
        assert "{not json" in result["text"]


class TestArchives:
    def test_zip_entries_listed(self, tmp_path):
        import zipfile

        f = tmp_path / "bundle.zip"
        with zipfile.ZipFile(f, "w") as z:
            z.writestr("README.md", "hi")
            z.writestr("data/a.csv", "a,b\n")
        result = preview.preview_file(f)
        assert result["kind"] == "archive"
        assert result["total"] == 2
        assert any("README.md" in e for e in result["entries"])

    def test_tar_entries_listed(self, tmp_path):
        import tarfile

        f = tmp_path / "bundle.tar"
        with tarfile.open(f, "w") as t:
            p = tmp_path / "x.txt"
            p.write_text("x", encoding="utf-8")
            t.add(p, arcname="x.txt")
        result = preview.preview_file(f)
        assert result["kind"] == "archive"
        assert any("x.txt" in e for e in result["entries"])


class TestBoundedReads:
    def test_too_large_file_refuses_preview(self, tmp_path):
        f = tmp_path / "big.csv"
        f.write_bytes(b"a,b\n" + b"1,2\n" * 200_000)
        result = preview.preview_file(f, max_bytes=1024)
        assert result["kind"] == "too_large"
        assert result["size_bytes"] > result["cap_bytes"]

    def test_binary_unknown_extension_is_unsupported(self, tmp_path):
        f = tmp_path / "blob.xyz"
        f.write_bytes(b"\x00\x01\x02\x03binary")
        result = preview.preview_file(f)
        assert result["kind"] == "unsupported"

    def test_empty_csv(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("", encoding="utf-8")
        result = preview.preview_file(f)
        assert result["kind"] == "tabular"
        assert result["rows"] == []


class TestMissingLibraries:
    def test_missing_openpyxl_shows_notice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(preview, "_have", lambda m: False)
        f = tmp_path / "book.xlsx"
        f.write_bytes(b"PK\x03\x04")  # minimal zip stub, never parsed
        result = preview.preview_file(f)
        assert result["kind"] == "missing"
        assert "openpyxl" in result["message"]

    def test_missing_pypdf_shows_notice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(preview, "_have", lambda m: False)
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        result = preview.preview_file(f)
        assert result["kind"] == "missing"
        assert "pypdf" in result["message"]


class TestImagesAndPdf:
    def test_png_preview_has_dimensions(self, tmp_path):
        pytest.importorskip("PIL.Image")
        from PIL import Image as PILImage

        f = tmp_path / "img.png"
        PILImage.new("RGB", (320, 200), (10, 20, 30)).save(f)
        result = preview.preview_file(f)
        assert result["kind"] == "image"
        assert result["width"] == 320
        assert result["height"] == 200
        assert result["thumbnail"]

    def test_pdf_page_count(self, tmp_path):
        pypdf = pytest.importorskip("pypdf")

        f = tmp_path / "doc.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(f, "wb") as handle:
            writer.write(handle)
        result = preview.preview_file(f)
        assert result["kind"] == "pdf"
        assert result["pages"] == 1


@pytest.fixture()
def card(qapp):
    from ui.preview import PreviewCard

    return PreviewCard()


class TestPreviewCard:
    def test_stub_shows_select_file(self, card):
        from PySide6.QtWidgets import QLabel

        labels = [w.text() for w in card.findChildren(QLabel)]
        assert any("Select a file" in t for t in labels)

    def test_csv_renders_table(self, card, tmp_path):
        from PySide6.QtWidgets import QPlainTextEdit

        f = tmp_path / "data.csv"
        f.write_text("name,age\nAnn,30\n", encoding="utf-8")
        card.set_path(f, rel="data.csv")
        edits = card.findChildren(QPlainTextEdit)
        assert edits and "Ann" in edits[0].toPlainText()

    def test_not_staged_state(self, card):
        kind = card.set_not_staged("x.csv")
        assert kind == "not_staged"

    def test_too_large_offers_open_folder(self, card, monkeypatch):
        monkeypatch.setattr(
            preview, "preview_file",
            lambda p, **kw: {"kind": "too_large", "size_bytes": 10**9, "cap_bytes": 1},
        )
        kind = card.set_path(__import__("pathlib").Path("whatever.csv"))
        assert kind == "too_large"
        assert card._open_btn.isHidden() is False

    def test_missing_library_shows(self, card, tmp_path, monkeypatch):
        monkeypatch.setattr(preview, "_have", lambda m: False)
        f = tmp_path / "book.xlsx"
        f.write_bytes(b"PK\x03\x04")
        kind = card.set_path(f)
        assert kind == "missing"
        from PySide6.QtWidgets import QPlainTextEdit

        assert "Missing" in card.findChildren(QPlainTextEdit)[0].toPlainText()


class TestRouting:
    def test_set_preview_logs_and_handles_missing(self, qapp, tmp_path):
        from ui.dataset_detail import DatasetDetailView

        v = DatasetDetailView.__new__(DatasetDetailView)
        staged = tmp_path / "staged"
        staged.mkdir()
        (staged / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        v._pid = "doi:x"
        v._logged = []
        from ui.preview import PreviewCard

        v._preview_card = PreviewCard()

        class _StubDl:
            def files_dir(self, pid):
                return staged

        v._dl_mgr = _StubDl()
        v._log_action = lambda a, n="", d=None: v._logged.append((a, n, d))
        v._show_preview_for_file("data.csv")
        assert ("preview_rendered", "data.csv")[:2] == (v._logged[0][0], v._logged[0][1])
        assert any(d and d.get("kind") == "tabular" for _a, _n, d in v._logged)

        v._show_preview_for_file("missing.csv")
        assert v._logged[-1][2]["kind"] == "not_staged"
