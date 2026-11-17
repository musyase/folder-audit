"""Create a self-contained, offline HTML report from a scan result."""

from __future__ import annotations

from collections import defaultdict
from html import escape
from typing import Any


STYLE = """
:root { color-scheme: light; --ink:#132b35; --muted:#526773; --line:#d9e4e8;
  --surface:#fff; --bg:#f3f7f8; --accent:#126a73; --soft:#dceff0; --warn:#815a19;
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); min-width:320px; }
a { color:var(--accent); }
.shell { max-width:1200px; margin:auto; padding:0 24px 72px; }
.mast { display:flex; justify-content:space-between; align-items:center; gap:20px;
  border-bottom:1px solid var(--line); padding:20px 0; }
.brand { font-weight:800; letter-spacing:-.04em; font-size:19px; }
.brand span { color:var(--accent); }
.local { border:1px solid #a5ccd0; color:#145e66; background:#e7f4f4;
  padding:6px 10px; border-radius:7px; font-size:12px; font-weight:700; }
.intro { padding:42px 0 28px; }
.intro h1 { font-size:clamp(32px,4.6vw,58px); line-height:1.04; letter-spacing:-.055em;
  margin:0 0 14px; max-width:730px; }
.intro p { margin:0; line-height:1.55; color:var(--muted); }
.source { font-family:ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap:anywhere;
  color:var(--ink); font-size:13px; margin-top:14px; }
.metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border:1px solid var(--line);
  background:var(--surface); border-radius:12px; overflow:hidden; margin:0 0 28px; }
.metric { padding:20px; border-right:1px solid var(--line); }
.metric:last-child { border-right:0; }
.metric strong { display:block; font-size:clamp(24px,3vw,34px); letter-spacing:-.04em; }
.metric span { color:var(--muted); font-size:12px; }
.grid { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr); gap:18px; }
.panel { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:22px; min-width:0; }
.panel h2 { font-size:20px; letter-spacing:-.025em; margin:0 0 5px; }
.panel-sub { color:var(--muted); font-size:13px; margin:0 0 20px; line-height:1.5; }
.group { border-top:1px solid var(--line); padding:15px 0; }
.group:first-of-type { border-top:0; padding-top:0; }
.group-head { display:flex; justify-content:space-between; gap:14px; align-items:baseline; }
.group-head strong { font-size:14px; }
.group-head span { color:var(--accent); font-size:12px; font-weight:700; white-space:nowrap; }
.paths { margin:8px 0 0; padding-left:17px; color:var(--muted); font:12px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap:anywhere; }
.folder { margin:14px 0 19px; }
.folder-top { display:flex; justify-content:space-between; gap:12px; font-size:13px; margin-bottom:7px; }
.folder-top span:first-child { font-family:ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap:anywhere; }
.folder-top span:last-child { color:var(--muted); white-space:nowrap; }
.bar { height:7px; background:#e9f0f2; border-radius:9px; overflow:hidden; }
.bar > span { display:block; height:100%; background:var(--accent); border-radius:9px; }
.files { margin-top:18px; }
.file-head { display:flex; justify-content:space-between; align-items:end; gap:18px; flex-wrap:wrap; margin-bottom:15px; }
.file-head h2 { margin:0 0 5px; }
.file-head p { margin:0; color:var(--muted); font-size:13px; }
.search { display:grid; gap:5px; font-size:12px; color:var(--muted); font-weight:700; min-width:min(310px,100%); }
.search input { width:100%; border:1px solid #9eb3bc; border-radius:8px; padding:10px 12px;
  background:#fff; color:var(--ink); font:inherit; font-size:14px; }
.search input:focus-visible { outline:3px solid #82c8cf; outline-offset:2px; }
.table-wrap { overflow:auto; max-height:500px; border:1px solid var(--line); border-radius:9px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { position:sticky; top:0; background:#eff5f6; color:#304a55; text-align:left;
  padding:11px 13px; font-size:12px; }
td { border-top:1px solid var(--line); padding:10px 13px; vertical-align:top; }
td:first-child { font-family:ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap:anywhere; }
td:last-child, th:last-child { text-align:right; white-space:nowrap; }
tr[hidden] { display:none; }
.empty { color:var(--muted); font-size:13px; padding:20px 0; }
.warning { border:1px solid #e7c983; background:#fff6df; color:var(--warn);
  padding:12px 15px; border-radius:9px; margin:0 0 18px; line-height:1.5; }
.foot { margin-top:22px; color:var(--muted); font-size:12px; line-height:1.5; }
@media (max-width:800px) { .grid { grid-template-columns:1fr; } .metrics { grid-template-columns:repeat(2,1fr); }
  .metric:nth-child(2) { border-right:0; } .metric:nth-child(-n+2) { border-bottom:1px solid var(--line); } }
@media (max-width:520px) { .shell { padding-inline:16px; } .intro { padding-top:30px; }
  .metric { padding:14px; } .panel { padding:17px; } .group-head { display:block; }
  .group-head span { display:block; margin-top:4px; } }
"""

SCRIPT = """
const search = document.querySelector('#file-search');
const rows = [...document.querySelectorAll('[data-file-row]')];
const count = document.querySelector('#visible-count');
search.addEventListener('input', () => {
  const query = search.value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const row of rows) {
    row.hidden = !row.dataset.path.toLocaleLowerCase().includes(query);
    if (!row.hidden) visible += 1;
  }
  count.textContent = String(visible);
});
"""


def _size(value: int) -> str:
    number = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024 or unit == "TiB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    raise AssertionError("unreachable")


def render_report(result: dict[str, Any], *, label: str | None = None) -> str:
    """Render the report without any network dependencies or injected file paths."""
    files = result["files"]
    groups = result["groups"]
    total = sum(item["size"] for item in files)
    folder_sizes: dict[str, int] = defaultdict(int)
    for item in files:
        folder = item["path"].split("/", 1)[0] if "/" in item["path"] else "(root)"
        folder_sizes[folder] += item["size"]
    folders = sorted(folder_sizes.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    largest = folders[0][1] if folders else 0

    group_html = "".join(
        '<div class="group"><div class="group-head"><strong>'
        + f'{len(group["paths"])} copies · {_size(group["size"])} each</strong>'
        + f'<span>{_size(group["reclaimable_bytes"])} reclaimable</span></div>'
        + '<ul class="paths">' + "".join(f'<li>{escape(path)}</li>' for path in group["paths"]) + '</ul></div>'
        for group in groups[:12]
    ) or '<p class="empty">No byte-identical files found.</p>'
    folder_html = "".join(
        f'<div class="folder"><div class="folder-top"><span>{escape(name)}</span><span>{_size(size)}</span></div>'
        f'<div class="bar"><span style="width:{max(2, round(size * 100 / largest)) if largest else 0}%"></span></div></div>'
        for name, size in folders
    ) or '<p class="empty">No files in this scan.</p>'
    file_html = "".join(
        f'<tr data-file-row data-path="{escape(item["path"], quote=True)}"><td>{escape(item["path"])}</td><td>{_size(item["size"])}</td></tr>'
        for item in sorted(files, key=lambda item: (-item["size"], item["path"]))
    )
    error_html = (
        f'<div class="warning" role="status">{len(result["errors"])} read errors. '
        'Results may be incomplete; inspect the JSON output before relying on this report.</div>'
        if result["errors"] else ""
    )
    title = escape(label or result["root"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>folder-audit · {title}</title><style>{STYLE}</style></head>
<body><div class="shell"><header class="mast"><div class="brand">folder<span>-audit</span></div><div class="local">Offline report</div></header>
<main><section class="intro"><h1>What is taking up space?</h1><p>A content-aware inventory of one folder. Search files and inspect identical copies.</p>
<div class="source">{title}</div></section>{error_html}
<section class="metrics" aria-label="Scan summary">
<div class="metric"><strong>{len(files):,}</strong><span>Files scanned</span></div>
<div class="metric"><strong>{_size(total)}</strong><span>Total size</span></div>
<div class="metric"><strong>{len(groups):,}</strong><span>Duplicate groups</span></div>
<div class="metric"><strong>{_size(result["reclaimable_bytes"])}</strong><span>Potentially reclaimable</span></div>
</section><div class="grid"><section class="panel"><h2>Identical files</h2><p class="panel-sub">SHA-256 matches. One copy per group is kept in the space estimate.</p>
{group_html}</section><section class="panel"><h2>Largest folders</h2><p class="panel-sub">Size of each top-level folder in this scan.</p>
{folder_html}</section></div>
<section class="panel files"><div class="file-head"><div><h2>All files</h2><p><span id="visible-count">{len(files)}</span> files shown · largest first</p></div>
<label class="search" for="file-search">Find a file<input id="file-search" type="search" placeholder="Type part of a path" autocomplete="off"></label></div>
<div class="table-wrap"><table><thead><tr><th scope="col">Relative path</th><th scope="col">Size</th></tr></thead><tbody>{file_html}</tbody></table></div></section>
<p class="foot">Created {escape(result["created_at"])} · {len(result["skipped_symlinks"])} symlinks skipped · No files were modified or uploaded.</p>
</main></div><script>{SCRIPT}</script></body></html>'''
