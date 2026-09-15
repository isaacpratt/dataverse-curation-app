"""Offline tests for the Dataverse client and download manager.

Parsing, lock semantics, quoting, safe extraction and checksum verification
are exercised with synthetic payloads - no network access required.
"""

import hashlib
import zipfile
from pathlib import Path

import pytest

from dataverse_client import (
    DataverseClient,
    extract_file_restrictions,
    locks_indicate_review,
    normalize_files,
    note_review_submission,
    parse_allowed_labels,
    parse_curation_states_csv,
    parse_curation_status,
    parse_dataset_versions,
    parse_ds_metadata_payload,
    parse_timestamps,
    parse_version_compare,
    search_item_state,
)
from download_manager import DownloadManager


def _dataset_entry(pid: str, title: str, files: list) -> dict:
    return {
        "status": "OK",
        "data": {
            "datasetId": 42,
            "datasetPersistentId": pid,
            "datasetVersion": {
                "versionState": "DRAFT",
                "metadataBlocks": {
                    "citation": {
                        "fields": [{"typeName": "title", "value": title}]
                    }
                },
                "files": files,
            },
        },
    }


def _file_entry(path: str, size: int, sha1: str) -> dict:
    directory, _, filename = path.rpartition("/")
    entry = {
        "filename": filename,
        "dataFile": {"id": 1, "filesize": size, "sha1": sha1},
    }
    if directory:
        entry["directoryLabel"] = directory
    return entry


def test_parse_ds_metadata_payload():
    payload = {
        "key1": _dataset_entry(
            "doi:10.5072/FK2/A",
            "Dataset A",
            [_file_entry("data/table.csv", 100, "a" * 40)],
        ),
        "key2": _dataset_entry("doi:10.5072/FK2/B", "", []),
        "ignored": "not a dataset",
    }

    datasets = parse_ds_metadata_payload(payload)

    assert len(datasets) == 2
    first = next(d for d in datasets if d["persistent_id"] == "doi:10.5072/FK2/A")
    assert first["title"] == "Dataset A"
    assert first["state"] == "DRAFT"
    assert first["file_count"] == 1
    assert first["total_size_bytes"] == 100
    assert first["files"][0]["path"] == "data/table.csv"
    assert first["files"][0]["checksum_type"] == "sha1"


def test_normalize_files_checksum_variants():
    dict_style = normalize_files(
        {
            "files": [
                {
                    "filename": "f.bin",
                    "dataFile": {
                        "id": 7,
                        "filesize": 5,
                        "contentType": "application/octet-stream",
                        "checksum": {"type": "MD5", "value": "d" * 32},
                    },
                }
            ]
        }
    )
    assert dict_style[0]["checksum_type"] == "md5"
    assert dict_style[0]["mime_type"] == "application/octet-stream"

    legacy_style = normalize_files(
        {"files": [{"filename": "g.txt", "dataFile": {"md5": "e" * 32}}]}
    )
    assert legacy_style[0]["checksum_type"] == "md5"


def test_locks_indicate_review():
    assert locks_indicate_review([{"lockType": "InReview"}])
    assert locks_indicate_review([{"lockType": "WORKFLOW"}, {"lockType": "inReview"}])
    assert not locks_indicate_review([])
    assert not locks_indicate_review([{"lockType": "WORKFLOW"}])


def test_parse_allowed_labels():
    assert parse_allowed_labels("Author contacted, Needs review,Ready for publish ") == [
        "Author contacted",
        "Needs review",
        "Ready for publish",
    ]
    assert parse_allowed_labels("") == []
    assert parse_allowed_labels(None) == []
    assert parse_allowed_labels(["not", "a", "string"]) == []
    # dupes dropped, order kept
    assert parse_allowed_labels("A, B, A") == ["A", "B"]


def test_parse_curation_status_object():
    payload = {
        "status": "OK",
        "data": {"label": "Author contacted", "createTime": "2026-09-01T10:00:00Z", "assigner": "curator1"},
    }
    assert parse_curation_status(payload) == {
        "label": "Author contacted",
        "time": "2026-09-01T10:00:00Z",
        "assigner": "curator1",
    }


def test_parse_curation_status_history_newest_wins():
    payload = {
        "status": "OK",
        "data": [
            {"label": "Needs review", "createTime": "2026-08-01", "assigner": "a"},
            {"label": "Author contacted", "createTime": "2026-09-01", "assigner": "b"},
        ],
    }
    parsed = parse_curation_status(payload)
    assert parsed is not None
    assert parsed["label"] == "Author contacted"
    assert parsed["assigner"] == "b"


def test_parse_curation_status_empty():
    assert parse_curation_status({"status": "OK", "data": None}) is None
    assert parse_curation_status({"status": "OK", "data": []}) is None
    assert parse_curation_status({"status": "OK", "data": {"label": "  "}}) is None
    assert parse_curation_status({}) is None


def _curation_csv() -> str:
    return (
        "Dataset,Creation Date,Modification Date,Curation Status,"
        "Curation Status Setter,Curation Status Create Time,admin\n"
        '"=HYPERLINK(""https://demo.borealisdata.ca/dataset.xhtml?persistentId=doi:10.5072/FK2/AAA"",""Alpha, First"")",'
        "2026-08-01,2026-09-01,Author contacted,curator1,2026-09-02 10:00:00,\n"
        '"=HYPERLINK(""https://demo.borealisdata.ca/dataset.xhtml?persistentId=doi:10.5072/FK2/BBB"",""Beta"")",'
        "2026-08-02,2026-09-02,,None,None,\n"
        '"=HYPERLINK(""https://demo.borealisdata.ca/dataset.xhtml?persistentId=doi:10.5072/FK2/CCC"",""Gamma"")",'
        "2026-08-03,2026-09-03,<none>,None,None,\n"
    )


def test_parse_curation_states_csv():
    rows = parse_curation_states_csv(_curation_csv())
    assert len(rows) == 3
    by_pid = {r["persistent_id"]: r for r in rows}
    assert by_pid["doi:10.5072/FK2/AAA"]["title"] == "Alpha, First"
    assert by_pid["doi:10.5072/FK2/AAA"]["label"] == "Author contacted"
    assert by_pid["doi:10.5072/FK2/AAA"]["label_time"] == "2026-09-02 10:00:00"
    assert by_pid["doi:10.5072/FK2/AAA"]["assigner"] == "curator1"
    # never labeled → empty label/time/assigner
    assert by_pid["doi:10.5072/FK2/BBB"]["label"] == ""
    assert by_pid["doi:10.5072/FK2/BBB"]["label_time"] == ""
    assert by_pid["doi:10.5072/FK2/BBB"]["assigner"] == ""
    # removed label (<none>) → also empty
    assert by_pid["doi:10.5072/FK2/CCC"]["label"] == ""


def test_parse_curation_states_csv_empty():
    assert parse_curation_states_csv("") == []
    assert parse_curation_states_csv("Dataset,Creation Date\n") == []


def _compare_payload() -> dict:
    return {
        "status": "OK",
        "data": {
            "oldVersion": {"versionNumber": "1.0", "versionState": "RELEASED"},
            "newVersion": {"versionNumber": "DRAFT", "versionState": "DRAFT"},
            "metadataChanges": [
                {
                    "blockName": "Citation Metadata",
                    "changed": [
                        {"fieldName": "Title", "oldValue": "Old title", "newValue": "New title"},
                        {"fieldName": "Description", "oldValue": None, "newValue": "Added"},
                    ],
                }
            ],
            "TermsOfAccess": {
                "changed": [{"fieldName": "Terms of Use", "oldValue": "A", "newValue": "B"}]
            },
            "filesAdded": [{"fileName": "new.csv", "filePath": "data", "fileId": 11}],
            "filesRemoved": [{"fileName": "old.sav", "fileId": 9}],
            "filesReplaced": [
                {"oldFile": {"fileName": "r.pdf", "fileId": 5}, "newFile": {"fileName": "r_v2.pdf", "fileId": 12}}
            ],
            "fileChanges": [
                {
                    "fileName": "img.png",
                    "fileId": 7,
                    "changed": [{"fieldName": "Description", "oldValue": "x", "newValue": "y"}],
                }
            ],
        },
    }


def test_parse_version_compare():
    diff = parse_version_compare(_compare_payload())
    assert diff is not None
    assert diff["old"]["number"] == "1.0"
    assert diff["new"]["state"] == "DRAFT"
    assert len(diff["metadata_changes"]) == 2
    assert diff["metadata_changes"][0]["block"] == "Citation Metadata"
    assert diff["metadata_changes"][0]["old"] == "Old title"
    assert diff["metadata_changes"][1]["old"] == ""  # None → ""
    assert diff["terms_changes"][0]["field"] == "Terms of Use"
    assert diff["files_added"][0]["name"] == "new.csv"
    assert diff["files_added"][0]["path"] == "data"
    assert diff["files_removed"][0]["name"] == "old.sav"
    assert diff["files_replaced"][0]["new"]["name"] == "r_v2.pdf"
    assert diff["file_changes"][0]["file"] == "img.png"
    assert diff["total_changes"] == 2 + 1 + 1 + 1 + 1 + 1


def test_parse_version_compare_empty():
    assert parse_version_compare({}) is None
    assert parse_version_compare({"status": "OK"}) is None
    diff = parse_version_compare(
        {"status": "OK", "data": {"oldVersion": {"versionNumber": "1.0"}, "newVersion": {}}}
    )
    assert diff is not None
    assert diff["total_changes"] == 0
    assert diff["metadata_changes"] == []
    assert diff["files_added"] == []


def test_search_item_state_plain_cases():
    assert search_item_state({"versionState": "DRAFT", "publicationStatuses": ["Draft"]}) == ("DRAFT", True)
    assert search_item_state({"versionState": "RELEASED", "publicationStatuses": ["Published"]}) == ("RELEASED", False)
    assert search_item_state({}) == ("", False)


def test_search_item_state_published_doc_with_draft():
    # Published doc shadows a new draft version: draft markers win.
    state, has_draft = search_item_state(
        {"versionState": "RELEASED", "publicationStatuses": ["Published", "Draft"]}
    )
    assert state == "DRAFT"
    assert has_draft is True


def test_search_item_state_in_review_status():
    state, has_draft = search_item_state(
        {"versionState": "DRAFT", "publicationStatuses": ["Draft", "In Review"]}
    )
    assert state == "In Review"
    assert has_draft is True


def test_parse_dataset_versions():
    data = [
        {"versionNumber": 1, "versionMinorNumber": 0, "versionState": "RELEASED",
         "createTime": "2024-01-01T10:00:00Z", "releaseTime": "2024-02-01T10:00:00Z"},
        {"versionNumber": 2, "versionMinorNumber": 0, "versionState": "DRAFT",
         "createTime": "2026-09-01T10:00:00Z", "lastUpdateTime": "2026-09-08T10:00:00Z"},
        {"versionState": "DEACCESSIONED", "createTime": "2023-01-01", "releaseTime": "2023-06-01"},
    ]
    versions = parse_dataset_versions(data)
    assert len(versions) == 3
    assert versions[0]["number"] == "1.0"
    assert versions[0]["release_time"] == "2024-02-01T10:00:00Z"
    assert versions[1]["number"] == "Draft"
    assert versions[2]["state"] == "DEACCESSIONED"
    assert parse_dataset_versions(None) == []
    assert parse_dataset_versions({}) == []
    assert parse_dataset_versions("nope") == []


def test_parse_timestamps():
    parsed = parse_timestamps(
        {
            "status": "OK",
            "data": {
                "createTime": "2024-01-01T10:00:00Z",
                "publicationTime": "2024-02-01T10:00:00Z",
                "globalIdCreateTime": "2024-02-01T10:00:01Z",
                "lastUpdateTime": "2026-09-01T10:00:00Z",
            },
        }
    )
    assert parsed["createTime"] == "2024-01-01T10:00:00Z"
    assert parsed["publicationTime"] == "2024-02-01T10:00:00Z"
    assert parsed["globalIdCreateTime"] == "2024-02-01T10:00:01Z"
    assert parsed["lastIndexTime"] == ""
    assert parse_timestamps({}) == {}
    assert parse_timestamps({"status": "OK"}) == {}


def test_extract_file_restrictions():
    assert extract_file_restrictions({}, {}) == {"embargo_date": "", "retention": ""}
    nested = extract_file_restrictions(
        {"filename": "a.csv"},
        {"id": 1, "embargo": {"dateAvailable": "2027-06-01", "reason": "x"}},
    )
    assert nested == {"embargo_date": "2027-06-01", "retention": ""}
    flat = extract_file_restrictions({"dateAvailable": "2028-01-15"}, {})
    assert flat["embargo_date"] == "2028-01-15"
    retention = extract_file_restrictions(
        {}, {"retention": {"retentionPeriod": "2029-03-01"}}
    )
    assert retention["retention"] == "2029-03-01"
    # unrelated dates are never mislabeled as embargo/retention
    plain = extract_file_restrictions(
        {}, {"id": 2, "creationDate": "2024-05-01", "publicationDate": "2024-06-01"}
    )
    assert plain == {"embargo_date": "", "retention": ""}


def test_note_review_submission():
    pid = "doi:10.80240/FK2/9MI1DN"
    note = {
        "type": "SUBMITTEDDS",
        "datasetPersistentIdentifier": pid,
        "datasetDisplayName": "Replication Data",
        "ownerAlias": "mcmaster",
        "ownerDisplayName": "McMaster University Dataverse",
        "sentTimestamp": "2026-09-03T12:00:00Z",
    }
    hit = note_review_submission(pid, note)
    assert hit is not None
    assert hit["time"] == "2026-09-03T12:00:00Z"
    assert hit["dataverse"] == "McMaster University Dataverse"
    assert hit["dataset"] == "Replication Data"
    # PID comparison is case-insensitive
    assert note_review_submission(pid.upper(), note) is not None
    # wrong dataset rejected
    assert note_review_submission("doi:10.80240/FK2/OTHER", note) is None
    # non-submission types rejected even for the right dataset
    assert note_review_submission(pid, {**note, "type": "PUBLISHEDDS"}) is None
    assert note_review_submission(pid, {**note, "type": "STATUSUPDATED"}) is None
    # missing structured fields rejected (no text fallback)
    assert note_review_submission(pid, {**note, "datasetPersistentIdentifier": ""}) is None
    assert note_review_submission(pid, {"type": "SUBMITTEDDS"}) is None
    assert note_review_submission(pid, {}) is None
    assert note_review_submission("", note) is None
    # requestor captured when present
    with_requestor = {
        **note,
        "requestorFirstName": "Isaac",
        "requestorLastName": "Pratt",
    }
    hit2 = note_review_submission(pid, with_requestor)
    assert hit2 is not None
    assert hit2["requestor"] == "Isaac Pratt"


class FakeClient:
    def __init__(self, inventory):
        self._inventory = inventory

    def get_file_inventory(self, persistent_id, version="draft"):
        return self._inventory


def test_size_cache_roundtrip(tmp_path):
    from storage import read_size_cache, write_size_entry

    assert read_size_cache(tmp_path) == {}
    write_size_entry(tmp_path, "doi:10.5072/FK2/A", 12345, 3)
    write_size_entry(tmp_path, "doi:10.5072/FK2/B", 0, 0)
    cache = read_size_cache(tmp_path)
    assert cache["doi:10.5072/FK2/A"] == {"size": 12345, "files": 3}
    assert cache["doi:10.5072/FK2/B"] == {"size": 0, "files": 0}
    # corrupt cache never raises
    (tmp_path / "dataset_sizes.json").write_text("not json", encoding="utf-8")
    assert read_size_cache(tmp_path) == {}


def test_quote_and_verify_with_fake_client(tmp_path):
    content = b"col_a,col_b\n1,2\n"
    staged = tmp_path / "ws" / "downloads" / "pid" / "files"
    staged.mkdir(parents=True)
    (staged / "table.csv").write_bytes(content)

    inventory = [
        {
            "path": "table.csv",
            "size_bytes": len(content),
            "checksum_type": "md5",
            "checksum_value": hashlib.md5(content).hexdigest(),
        }
    ]
    manager = DownloadManager(FakeClient(inventory), tmp_path / "ws")

    quote = manager.quote("pid")
    assert quote.file_count == 1
    assert quote.total_size_bytes == len(content)

    ok, problems, warnings = manager.verify("pid")
    assert ok
    assert problems == []
    assert warnings == []

    (staged / "table.csv").write_bytes(b"tampered")
    ok, problems, warnings = manager.verify("pid")
    assert not ok
    assert any("checksum mismatch" in p for p in problems)


def test_verify_detects_missing_file(tmp_path):
    inventory = [
        {"path": "gone.csv", "size_bytes": 10, "checksum_type": "", "checksum_value": ""}
    ]
    manager = DownloadManager(FakeClient(inventory), tmp_path / "ws")
    ok, problems, warnings = manager.verify("any")
    assert not ok
    assert any(p.startswith("missing") for p in problems)


def test_safe_extract_blocks_zip_slip(tmp_path):
    malicious = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape.txt", "nope")

    dest = tmp_path / "dest"
    with pytest.raises(RuntimeError, match="unsafe archive entry"):
        DownloadManager._safe_extract(malicious, dest)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_ok(tmp_path):
    bundle = tmp_path / "ok.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("sub/inner.txt", "fine")

    dest = tmp_path / "dest"
    DownloadManager._safe_extract(bundle, dest)
    assert (dest / "sub" / "inner.txt").read_text() == "fine"


def test_normalize_files_tabular_unf():
    records = normalize_files(
        {
            "files": [
                {
                    "filename": "eco.tab",
                    "dataFile": {
                        "id": 9,
                        "filesize": 100,
                        "md5": "a" * 32,
                        "tabularData": True,
                        "UNF": "UNF:6:abc==",
                        "originalFileFormat": "application/x-spss-sav",
                        "originalFileName": "eco.sav",
                    },
                },
                {
                    "filename": "plain.csv",
                    "dataFile": {"id": 10, "filesize": 10, "md5": "b" * 32},
                },
            ]
        }
    )
    tab = records[0]
    assert tab["tabular"] is True
    assert tab["unf"] == "UNF:6:abc=="
    assert tab["original_format"] == "application/x-spss-sav"
    assert tab["original_name"] == "eco.sav"
    plain = records[1]
    assert plain["tabular"] is False
    assert plain["unf"] == ""
    # lowercase unf fallback
    lower = normalize_files(
        {"files": [{"filename": "x.tab", "dataFile": {"unf": "UNF:6:z=="}}]}
    )
    assert lower[0]["unf"] == "UNF:6:z=="


def test_verify_mismatch_reports_hashes_and_tabular_note(tmp_path):
    content = b"col_a\n1\n"
    staged = tmp_path / "ws" / "downloads" / "pid" / "files"
    staged.mkdir(parents=True)
    (staged / "eco.tab").write_bytes(content)
    (staged / "ok.csv").write_bytes(content)

    inventory = [
        {
            "path": "eco.tab",
            "size_bytes": len(content),
            "checksum_type": "md5",
            "checksum_value": "0" * 32,
            "tabular": True,
            "unf": "UNF:6:abc==",
            "original_format": "application/x-spss-sav",
        },
        {
            "path": "ok.csv",
            "size_bytes": len(content),
            "checksum_type": "md5",
            "checksum_value": hashlib.md5(content).hexdigest(),
        },
    ]
    manager = DownloadManager(FakeClient(inventory), tmp_path / "ws")
    ok, problems, warnings = manager.verify("pid")
    assert ok
    assert problems == []
    assert len(warnings) == 1
    line = warnings[0]
    assert "checksum mismatch: eco.tab" in line
    assert "md5 expected " in line and " got " in line
    assert "UNF:6:abc==" in line
    assert "server-regenerated" in line
    assert "application/x-spss-sav" in line


def test_missing_files_and_fully_staged(tmp_path):
    content = b"0123456789"
    staged = tmp_path / "ws" / "downloads" / "pid" / "files"
    staged.mkdir(parents=True)
    (staged / "a.csv").write_bytes(content)
    (staged / "b.csv").write_bytes(b"changed-size")

    inventory = [
        {"path": "a.csv", "size_bytes": len(content)},
        {"path": "b.csv", "size_bytes": 999},
        {"path": "c.csv", "size_bytes": 10},
    ]
    manager = DownloadManager(FakeClient(inventory), tmp_path / "ws")
    assert manager.missing_files("pid", inventory) == ["b.csv", "c.csv"]
    assert not manager.is_fully_staged("pid", inventory)
    (staged / "b.csv").write_bytes(b"x" * 999)
    (staged / "c.csv").write_bytes(b"y" * 10)
    assert manager.is_fully_staged("pid", inventory)


def test_download_originals_skips_staged_and_nontabular(tmp_path):
    staged = tmp_path / "ws" / "downloads" / "pid" / "files"
    staged.mkdir(parents=True)
    (staged / "eco.sav").write_bytes(b"already here")

    class OrigClient(FakeClient):
        def __init__(self, inventory):
            super().__init__(inventory)
            self.fetched = []

        def download_datafile_original(self, file_id, dest, progress=None):
            self.fetched.append(file_id)
            Path(dest).write_bytes(b"orig-bytes")
            return dest

    inventory = [
        {"path": "eco.tab", "id": "9", "tabular": True,
         "original_name": "eco.sav", "original_size": 12},
        {"path": "plain.csv", "id": "10", "tabular": False,
         "original_name": "", "original_size": 0},
        {"path": "new.tab", "id": "11", "tabular": True,
         "original_name": "new.sav", "original_size": 10},
    ]
    client = OrigClient(inventory)
    manager = DownloadManager(client, tmp_path / "ws")
    got = manager.download_originals("pid", inventory)
    # eco.sav already staged with matching size -> skipped (but reported);
    # plain.csv not tabular -> skipped; new.sav fetched
    assert client.fetched == ["11"]
    assert got == ["eco.sav", "new.sav"]
    assert (staged / "new.sav").read_bytes() == b"orig-bytes"


def test_table_layout_roundtrip(tmp_path):
    from storage import restore_table_state, save_table_state

    class FakeHeader:
        def __init__(self, widths):
            self._widths = list(widths)
            self.blocked = False

        def count(self):
            return len(self._widths)

        def sectionSize(self, i):
            return self._widths[i]

        def resizeSection(self, i, w):
            self._widths[i] = w

        def blockSignals(self, b):
            self.blocked = b
            return False

    header = FakeHeader([100, 200, 300])
    save_table_state(tmp_path, "dataset_files", header)
    header2 = FakeHeader([50, 50, 50])
    restore_table_state(tmp_path, "dataset_files", header2)
    assert header2._widths == [100, 200, 300]
    assert header2.blocked is False
    # unknown name / corrupt file never raise
    restore_table_state(tmp_path, "nope", FakeHeader([1]))
    (tmp_path / "table_layout.json").write_text("{bad", encoding="utf-8")
    restore_table_state(tmp_path, "dataset_files", FakeHeader([1]))