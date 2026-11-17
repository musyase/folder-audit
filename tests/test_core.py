import json
import os
from pathlib import Path

import pytest

from folder_audit.cli import main
from folder_audit.core import compare, duplicate_groups, load_snapshot, scan


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
