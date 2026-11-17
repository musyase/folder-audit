"""Regenerate the public, synthetic HTML example in docs/demo.html."""

from __future__ import annotations

import tempfile
from pathlib import Path

from folder_audit.core import duplicate_groups
from folder_audit.report import render_report


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="folder-audit-example-") as temporary:
        folder = Path(temporary)
        samples = {
            "exports/report-q1.pdf": b"SAMPLE PDF CONTENT\n" * 1600,
            "backup/report-q1.pdf": b"SAMPLE PDF CONTENT\n" * 1600,
            "images/chart.png": b"SAMPLE IMAGE CONTENT\n" * 400,
            "backup/chart.png": b"SAMPLE IMAGE CONTENT\n" * 400,
            "notes/plan.txt": b"A plan for the next release.\n" * 15,
            "notes/changelog.txt": b"Fixed parsing and export.\n" * 10,
        }
        for name, content in samples.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        result = duplicate_groups(folder)
        result["created_at"] = "2026-11-18T00:00:00+00:00"
        output = repo / "docs" / "demo.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_report(result, label="Sample export folder"), encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
