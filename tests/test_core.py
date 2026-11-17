import json
import os
from pathlib import Path

import pytest

from folder_audit.cli import main
from folder_audit.core import compare, duplicate_groups, load_snapshot, scan
from folder_audit.report import render_report


def test_duplicate_detection_checks_content_not_just_size(tmp_path: Path):
    (tmp_path / "a.txt").write_bytes(b"same")
    (tmp_path / "b.txt").write_bytes(b"same")
    (tmp_path / "c.txt").write_bytes(b"else")

    result = duplicate_groups(tmp_path)

    assert len(result["groups"]) == 1
    assert result["groups"][0]["paths"] == ["a.txt", "b.txt"]
    assert result["reclaimable_bytes"] == 4


def test_snapshot_diff_uses_hash_when_mtime_is_unchanged(tmp_path: Path):
    path = tmp_path / "file.txt"
    path.write_text("one", encoding="utf-8")
    before = scan(tmp_path)
    mtime_ns = path.stat().st_mtime_ns
    path.write_text("two", encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")

    after = scan(tmp_path)

    assert compare(before, after) == {"added": ["new.txt"], "removed": [], "changed": ["file.txt"]}


def test_exclusions_and_symlinks_are_respected(tmp_path: Path):
    (tmp_path / "keep.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "ignore.log").write_text("skip", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "nested.txt").write_text("skip", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(tmp_path / "keep.txt")
    except (OSError, NotImplementedError):
        pass  # Windows may require developer mode for symlinks.

    result = scan(tmp_path, exclude=["*.log", "ignored"])

    assert [item["path"] for item in result["files"]] == ["keep.txt"]
    if link.is_symlink():
        assert result["skipped_symlinks"] == ["link.txt"]


def test_snapshot_command_excludes_its_own_output(tmp_path: Path):
    (tmp_path / "data.txt").write_text("data", encoding="utf-8")
    output = tmp_path / "snapshot.json"

    assert main(["snapshot", str(tmp_path), str(output)]) == 0
    assert [item["path"] for item in load_snapshot(output)["files"]] == ["data.txt"]
    assert main(["snapshot", str(tmp_path), str(output)]) == 0
    assert [item["path"] for item in load_snapshot(output)["files"]] == ["data.txt"]


def test_dupes_command_excludes_its_own_report(tmp_path: Path):
    (tmp_path / "a").write_bytes(b"same")
    (tmp_path / "b").write_bytes(b"same")
    output = tmp_path / "dupes.json"

    assert main(["dupes", str(tmp_path), "--json", str(output)]) == 0
    assert main(["dupes", str(tmp_path), "--json", str(output)]) == 0
    assert [item["path"] for item in json.loads(output.read_text())["files"]] == ["a", "b"]


def test_rejects_invalid_and_duplicate_snapshot_entries(tmp_path: Path):
    output = tmp_path / "bad.json"
    output.write_text(json.dumps({"version": 1, "hashed": True, "files": [
        {"path": "x", "sha256": "abc"}, {"path": "x", "sha256": "abc"}
    ]}), encoding="utf-8")

    with pytest.raises(ValueError, match="repeated path"):
        load_snapshot(output)


def test_report_command_is_self_contained_and_excludes_its_output(tmp_path: Path):
    (tmp_path / "a.txt").write_bytes(b"same")
    (tmp_path / "b.txt").write_bytes(b"same")
    output = tmp_path / "report.html"

    assert main(["report", str(tmp_path), str(output), "--label", "Example folder"]) == 0
    assert main(["report", str(tmp_path), str(output), "--label", "Example folder"]) == 0
    html = output.read_text(encoding="utf-8")
    assert "Example folder" in html
    assert str(tmp_path) not in html
    assert 'id="file-search"' in html
    assert "2 copies" in html
    assert 'data-path="report.html"' not in html


def test_report_escapes_untrusted_file_names_and_labels():
    result = {
        "root": "secret-root", "created_at": "2026-11-18T00:00:00+00:00",
        "files": [{"path": '<script>alert("x")</script>.txt', "size": 4}],
        "groups": [], "reclaimable_bytes": 0, "errors": [], "skipped_symlinks": [],
    }

    html = render_report(result, label="<unsafe>")

    assert "secret-root" not in html
    assert "&lt;unsafe&gt;" in html
    assert '&lt;script&gt;alert(&quot;' in html
    assert '<script>alert("x")</script>' not in html
