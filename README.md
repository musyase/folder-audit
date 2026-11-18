# folder-audit

A small, offline tool for answering two practical questions: **which files are identical?** and **what changed in this folder?** It reads files but never deletes or moves them. Useful for export folders, backups, course materials, and project artifacts.

**Try the interactive report:** [open a synthetic example](https://musyase.github.io/folder-audit/demo.html). It uses invented file names and contents; the report itself works offline.

**Why this project exists:** comparing file names or sizes alone misses modified files and produces false duplicate matches. `folder-audit` uses SHA-256 for content comparison. Duplicate scanning hashes only files with matching sizes, so unique-size files are skipped.

## Install

Requires Python 3.11 or newer. No runtime dependencies or account are needed.

```bash
python -m pip install -e .
```

On Windows, use `py -m pip install -e .` if the `python` command is unavailable.
You can run every example as `py -m folder_audit ...` if the installed script directory is not on `PATH`.

## Find duplicate files

```bash
folder-audit dupes ./exports --exclude '*.tmp' --exclude '.git' --json duplicates.json
```

Example output:

```text
4 bytes each, 2 copies, SHA-256 0967115f2813a3541eaef77de9d9d5773f1c0c04314b0bbfe4ff3b3b1c55b5d5
  copy/a.txt
  copy/b.txt
1 groups; 4 potentially reclaimable bytes
```

`reclaimable_bytes` is an estimate assuming one copy from each group is kept. The tool does not remove anything.

## Compare folder states

```bash
folder-audit snapshot ./exports before.json
# Make changes in ./exports.
folder-audit snapshot ./exports after.json
folder-audit diff before.json after.json --json changes.json
```

The diff lists added, removed, moved, and content-changed paths. A move is reported when one removed path and one added path share a unique content hash. If several paths share that hash, the tool leaves them as added and removed rather than guessing which file moved. Changes to timestamps alone do not count as changed. Snapshot JSON includes the scan time, original root, relative paths, file sizes, nanosecond modification times, SHA-256 hashes, skipped symlinks, and read errors.

## Open an HTML report

```bash
folder-audit report ./exports report.html --exclude '.git'
```

Open `report.html` in a browser to search all files, inspect duplicate groups, and see which top-level folders take the most space. The report is one HTML file with no external scripts, fonts, or requests. It contains file names and sizes, so keep reports of private folders private. Use `--label "My exports"` to replace the displayed absolute folder path.

The example page in `docs/demo.html` is generated from synthetic files with `python scripts/build_demo.py`.

## Behavior and limits

- Local files only; no cloud access or telemetry.
- Symlinks are recorded as skipped and are never followed. This avoids traversing outside the selected folder or looping through linked directories.
- Exclude patterns match relative paths or individual names. Use repeated `--exclude` flags.
- If a file changes during hashing, it is reported as an error. An incomplete scan still writes a snapshot and exits with code `2`; inspect its `errors` field before relying on the result.
- Large snapshots read every file to calculate hashes. Duplicate scans first group by size to avoid hashing files that cannot be duplicates.
- A content match is inferred from matching SHA-256 digests; byte-for-byte comparison is not performed after hashing.

## Development

```bash
python -m pip install -e . pytest
python -m pytest -q
```

GitHub Actions runs the tests on Windows and Ubuntu with Python 3.11 and 3.14.
