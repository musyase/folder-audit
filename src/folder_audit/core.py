"""Filesystem scanning and snapshot comparison.

No files are modified by this module. Symlinks are deliberately never followed.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 1
CHUNK_SIZE = 1024 * 1024


def _excluded(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(Path(relative).name, pattern)
               for pattern in patterns)


def _hash_file(path: Path, expected_size: int, expected_mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    after = path.stat()
    if after.st_size != expected_size or after.st_mtime_ns != expected_mtime_ns:
        raise OSError("file changed while it was being hashed")
    return digest.hexdigest()


def scan(root: Path, *, hashes: bool = True, exclude: list[str] | None = None) -> dict[str, Any]:
    """Return a deterministic inventory of regular files below *root*."""
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    patterns = exclude or []
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    skipped_symlinks: list[str] = []

    def walk_error(exc: OSError) -> None:
        errors.append({"path": str(exc.filename or root), "error": str(exc)})

    for current, dirs, names in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        current_path = Path(current)
        kept_dirs = []
        for name in sorted(dirs):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if _excluded(relative, patterns):
                continue
            if path.is_symlink():
                skipped_symlinks.append(relative)
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs

        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if _excluded(relative, patterns):
                continue
            try:
                if path.is_symlink():
                    skipped_symlinks.append(relative)
                    continue
                stat = path.stat()
                if not path.is_file():
                    continue
                item: dict[str, Any] = {
                    "path": relative,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
                if hashes:
                    item["sha256"] = _hash_file(path, stat.st_size, stat.st_mtime_ns)
                files.append(item)
            except OSError as exc:
                errors.append({"path": relative, "error": str(exc)})

    files.sort(key=lambda item: item["path"])
    errors.sort(key=lambda item: item["path"])
    skipped_symlinks.sort()
    return {
        "version": SNAPSHOT_VERSION,
        "root": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hashed": hashes,
        "files": files,
        "errors": errors,
        "skipped_symlinks": skipped_symlinks,
    }


def duplicate_groups(root: Path, *, exclude: list[str] | None = None) -> dict[str, Any]:
    """Hash only files whose sizes match; report byte-identical groups."""
    result = scan(root, hashes=False, exclude=exclude)
    by_size: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in result["files"]:
        by_size[item["size"]].append(item)

    by_digest: dict[tuple[int, str], list[str]] = defaultdict(list)
    root_path = Path(result["root"])
    for size, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        for item in candidates:
            try:
                path = root_path.joinpath(*item["path"].split("/"))
                digest = _hash_file(path, item["size"], item["mtime_ns"])
                by_digest[(size, digest)].append(item["path"])
            except OSError as exc:
                result["errors"].append({"path": item["path"], "error": str(exc)})

    result["errors"].sort(key=lambda item: item["path"])
    result["groups"] = [
        {"size": size, "sha256": digest, "paths": sorted(paths), "reclaimable_bytes": size * (len(paths) - 1)}
        for (size, digest), paths in by_digest.items() if len(paths) > 1
    ]
    result["groups"].sort(key=lambda group: (-group["reclaimable_bytes"], group["paths"]))
    result["reclaimable_bytes"] = sum(group["reclaimable_bytes"] for group in result["groups"])
    return result


def load_snapshot(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != SNAPSHOT_VERSION or data.get("hashed") is not True:
        raise ValueError("unsupported snapshot: expected a hashed folder-audit v1 snapshot")
    if not isinstance(data.get("files"), list):
        raise ValueError("invalid snapshot: files must be a list")
    seen: set[str] = set()
    for item in data["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise ValueError("invalid snapshot: each file needs path and sha256")
        if item["path"] in seen:
            raise ValueError(f"invalid snapshot: repeated path {item['path']}")
        seen.add(item["path"])
    return data


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old_files = {item["path"]: item for item in before["files"]}
    new_files = {item["path"]: item for item in after["files"]}
    old_paths, new_paths = set(old_files), set(new_files)
    added = new_paths - old_paths
    removed = old_paths - new_paths
    old_by_hash: dict[str, list[str]] = defaultdict(list)
    new_by_hash: dict[str, list[str]] = defaultdict(list)
    for path in old_paths:
        old_by_hash[old_files[path]["sha256"]].append(path)
    for path in new_paths:
        new_by_hash[new_files[path]["sha256"]].append(path)
    moved = []
    for digest in old_by_hash.keys() & new_by_hash.keys():
        old_matches, new_matches = old_by_hash[digest], new_by_hash[digest]
        if len(old_matches) == len(new_matches) == 1 and old_matches[0] in removed and new_matches[0] in added:
            source, destination = old_matches[0], new_matches[0]
            moved.append({"from": source, "to": destination})
            removed.remove(source)
            added.remove(destination)
    return {
        "added": sorted(added),
        "removed": sorted(removed),
        "moved": sorted(moved, key=lambda item: (item["from"], item["to"])),
        "changed": sorted(path for path in old_paths & new_paths
                          if old_files[path]["sha256"] != new_files[path]["sha256"]),
    }
