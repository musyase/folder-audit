"""Command line interface for folder-audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .core import compare, duplicate_groups, load_snapshot, scan
from .report import render_report


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A partially written snapshot must never replace a good one.
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_json(path: Path, data: dict) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="folder-audit", description="Inventory files, find duplicates, compare snapshots.")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="save a content-hashed folder inventory")
    snapshot.add_argument("folder", type=Path)
    snapshot.add_argument("output", type=Path)
    snapshot.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    dupes = commands.add_parser("dupes", help="find byte-identical files")
    dupes.add_argument("folder", type=Path)
    dupes.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    dupes.add_argument("--json", type=Path, metavar="FILE", help="write full machine-readable result")
    report = commands.add_parser("report", help="create a self-contained HTML inventory")
    report.add_argument("folder", type=Path)
    report.add_argument("output", type=Path)
    report.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    report.add_argument("--label", help="display name for the scanned folder")
    diff = commands.add_parser("diff", help="compare two hashed snapshots")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--json", type=Path, metavar="FILE")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            # Exclude the output itself when it resides inside the scanned folder.
            excluded = list(args.exclude)
            root = args.folder.expanduser().resolve(strict=True)
            output = args.output.expanduser().resolve()
            if output.is_relative_to(root):
                excluded.append(output.relative_to(root).as_posix())
            result = scan(root, exclude=excluded)
            _write_json(output, result)
            print(f"Saved {len(result['files'])} files to {output}")
            if result["errors"]:
                print(f"Warning: {len(result['errors'])} files could not be scanned", file=sys.stderr)
                return 2
            return 0
        if args.command in {"dupes", "report"}:
            excluded = list(args.exclude)
            report_output = args.output if args.command == "report" else args.json
            if report_output:
                root = args.folder.expanduser().resolve(strict=True)
                output = report_output.expanduser().resolve()
                if output.is_relative_to(root):
                    excluded.append(output.relative_to(root).as_posix())
            result = duplicate_groups(args.folder, exclude=excluded)
            if args.command == "report":
                _write_text(args.output, render_report(result, label=args.label))
                print(f"Saved HTML report to {args.output}")
                if result["errors"]:
                    print(f"Warning: {len(result['errors'])} files could not be scanned", file=sys.stderr)
                    return 2
                return 0
            if args.json:
                _write_json(args.json, result)
            for group in result["groups"]:
                print(f"{group['size']} bytes each, {len(group['paths'])} copies, SHA-256 {group['sha256']}")
                for path in group["paths"]:
                    print(f"  {path}")
            print(f"{len(result['groups'])} groups; {result['reclaimable_bytes']} potentially reclaimable bytes")
            if result["errors"]:
                print(f"Warning: {len(result['errors'])} files could not be scanned", file=sys.stderr)
                return 2
            return 0
        result = compare(load_snapshot(args.before), load_snapshot(args.after))
        if args.json:
            _write_json(args.json, result)
        for kind in ("added", "removed", "changed"):
            print(f"{kind}: {len(result[kind])}")
            for path in result[kind]:
                print(f"  {path}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"folder-audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
