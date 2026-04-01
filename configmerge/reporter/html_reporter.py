"""
configmerge.reporter.html_reporter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generates a self-contained HTML diff report.

Layout:
  - Fixed page header + summary bar
  - Two-column body:
      LEFT  — sticky sidebar: base-dir groups, file list, search
      RIGHT — toolbar + collapsible file sections
  - Per-file section:
      "Show Full Config" toggle — switches between changes-only and full
      merged file content (with changed lines annotated)
  - Multi-base: sidebar groups files by base dir; sections labelled by base
  - Inline CSS + vanilla JS (no external dependencies)
"""

from __future__ import annotations

import difflib
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models import MergeConfig, MergeResult, ReportEntry, EntryType


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px;
       background: #f4f6f9; color: #222; }

/* ── TOP BAR ────────────────────────────────── */
.page-header { background: #1e2a3a; color: #fff; padding: 16px 24px; position: sticky;
               top: 0; z-index: 200; }
.page-header h1 { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
.page-header .meta { font-size: 11px; color: #9ab; display: flex; gap: 20px; flex-wrap: wrap; }
.page-header .meta label { color: #6a8fa8; margin-right: 4px; }

/* ── SUMMARY ────────────────────────────────── */
.summary { background: #fff; border-bottom: 1px solid #dde3ed;
           padding: 12px 24px; display: flex; gap: 18px; flex-wrap: wrap;
           align-items: center; }
.stat { display: flex; flex-direction: column; align-items: center; min-width: 72px; }
.stat .num { font-size: 20px; font-weight: 700; color: #1e2a3a; }
.stat .lbl { font-size: 10px; color: #777; text-transform: uppercase;
             letter-spacing: .4px; margin-top: 2px; }
.stat.err .num { color: #c62828; }
.stat-div { width: 1px; background: #dde3ed; align-self: stretch; }

/* ── LAYOUT ─────────────────────────────────── */
.layout { display: flex; }
.sidebar { width: 270px; flex-shrink: 0; position: sticky; top: 58px;
           height: calc(100vh - 58px); overflow-y: auto;
           background: #fff; border-right: 1px solid #dde3ed; }
.main { flex: 1; min-width: 0; }

/* ── SIDEBAR ─────────────────────────────────── */
.sidebar-title { padding: 10px 14px 6px; font-size: 11px; font-weight: 700;
                 color: #1e2a3a; text-transform: uppercase; letter-spacing: .6px;
                 border-bottom: 1px solid #eef0f4; }
.sidebar-search { padding: 6px 10px; border-bottom: 1px solid #eef0f4; }
.sidebar-search input { width: 100%; padding: 4px 8px; border: 1px solid #c0c8d8;
                        border-radius: 4px; font-size: 12px; background: #f9fafc; }
/* ── FILE TREE ─────────────────────────────── */
.tree-root { padding: 4px 0 8px; }
.tree-dir-hdr { display: flex; align-items: center; gap: 5px;
                cursor: pointer; user-select: none; font-size: 12px;
                color: #1e2a3a; font-weight: 600;
                border-bottom: 1px solid #eef0f4;
                white-space: nowrap; overflow: hidden; }
.tree-dir-hdr:hover { background: #eef2f8; }
.tree-chevron { font-size: 9px; flex-shrink: 0; display: inline-block;
                transition: transform .15s; width: 10px; text-align: center; }
.tree-dir.closed > .tree-dir-body { display: none; }
.tree-dir.closed > .tree-dir-hdr .tree-chevron { transform: rotate(-90deg); }
.tree-file { display: flex; align-items: center; font-size: 12px; color: #444;
             cursor: pointer; white-space: nowrap; overflow: hidden;
             border-bottom: 1px solid #f4f6f9; }
.tree-file:hover { background: #eef2f8; color: #1e2a3a; }
.tree-file.active { background: #1e2a3a; color: #fff; }
.tree-file .fn { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.tree-file .sbadge { flex-shrink: 0; font-size: 10px; background: #e0e6f0;
                     color: #555; border-radius: 8px; padding: 0 6px; margin-right: 6px; }
.tree-file.active .sbadge { background: rgba(255,255,255,.2); color: #fff; }

/* ── TOOLBAR ─────────────────────────────────── */
.toolbar { background: #fff; border-bottom: 1px solid #dde3ed;
           padding: 9px 24px; display: flex; gap: 7px; align-items: center;
           flex-wrap: wrap; }
.toolbar button { padding: 4px 12px; border: 1px solid #c0c8d8; border-radius: 4px;
                  background: #f4f6f9; cursor: pointer; font-size: 11px; color: #444; }
.toolbar button:hover { background: #e8ecf4; }
.toolbar button.active { background: #1e2a3a; color: #fff; border-color: #1e2a3a; }
.spacer { flex: 1; }

/* ── FILE SECTION ────────────────────────────── */
.file-section { margin: 14px 24px; border: 1px solid #dde3ed;
                border-radius: 6px; background: #fff; overflow: hidden; }
.file-hdr { background: #eef2f8; padding: 10px 14px; cursor: pointer;
            display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.file-hdr:hover { background: #e3e9f4; }
.file-hdr .fname { font-weight: 600; font-size: 13px; color: #1e2a3a; flex: 1;
                   min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-hdr .badge { font-size: 11px; background: #1e2a3a; color: #fff;
                   border-radius: 10px; padding: 2px 9px; flex-shrink: 0; }
.file-hdr .base-tag { font-size: 10px; background: #e8f4fd; color: #1565c0;
                       border-radius: 3px; padding: 1px 7px; flex-shrink: 0; }
.chevron { font-size: 10px; color: #999; transition: transform .2s; flex-shrink: 0; }
.file-section.collapsed .file-body { display: none; }
.file-section.collapsed .chevron { transform: rotate(-90deg); }
.full-cfg-btn { padding: 3px 10px; border: 1px solid #c0c8d8; border-radius: 4px;
                background: #f4f6f9; cursor: pointer; font-size: 11px; color: #444;
                flex-shrink: 0; }
.full-cfg-btn:hover { background: #e8ecf4; }
.full-cfg-btn.active { background: #4a7aab; color: #fff; border-color: #4a7aab; }

/* ── CHANGE ROWS ─────────────────────────────── */
.file-body .view-label { padding: 5px 14px; font-size: 11px; color: #888;
                          background: #fafbfc; border-bottom: 1px solid #eef0f4; }
.change-row { border-top: 1px solid #eef0f4; }
.change-row.first { border-top: none; }
.chg-hdr { padding: 6px 14px; background: #f9fafc; font-size: 11px;
           display: flex; align-items: center; gap: 7px;
           border-bottom: 1px solid #eef0f4; flex-wrap: wrap; }
.param-name { font-weight: 600; color: #333; font-family: monospace; font-size: 12px; }
.tag { padding: 2px 7px; border-radius: 3px; font-size: 10px; font-weight: 600;
       text-transform: uppercase; letter-spacing: .4px; }
.tag.replaced  { background: #e8f4fd; color: #1565c0; }
.tag.base-only { background: #e8f5e9; color: #1b5e20; }
.tag.rel-only  { background: #fff3e0; color: #e65100; }
.tag.error     { background: #ffebee; color: #b71c1c; }
.tag.dup       { background: #fce4ec; color: #880e4f; }
.tag.group     { background: #ede7f6; color: #4527a0; }
.tag.ns        { background: #fffde7; color: #f57f17; }
.sect-label    { color: #888; font-size: 11px; }
.cbadge { display: inline-block; font-size: 10px; background: #fff3cd; color: #856404;
          border: 1px solid #ffc107; border-radius: 3px; padding: 0 5px; }

/* ── DIFF TABLE ──────────────────────────────── */
.diff-table { width: 100%; border-collapse: collapse;
              font-family: 'Courier New', monospace; font-size: 12px; }
.diff-table .col-hdr { padding: 5px 14px; background: #f0f2f6;
                       font-size: 10px; font-weight: 600; color: #555;
                       text-transform: uppercase; letter-spacing: .4px; width: 50%; }
.diff-table .col-hdr.rel { border-right: 2px solid #dde3ed; }
.diff-table td { padding: 7px 14px; vertical-align: top; width: 50%;
                 line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.diff-table td.rel-col { border-right: 2px solid #dde3ed; background: #fafbfc; }
.diff-table td.mrg-col { background: #fdfffe; }

/* ── HIGHLIGHTS ──────────────────────────────── */
.changed     { background: #ffe066; padding: 0 2px; border-radius: 2px; font-weight: bold; }
.added-row td    { background: #f0fff4 !important; }
.added-row .rel-col { background: #f9fafc !important; color: #aaa; }
.relonly-row td  { background: #fff8f0 !important; }
.error-row td    { background: #fff5f5 !important; }
.grp-add .rel-col { color: #aaa; font-style: italic; }
.grp-add .mrg-col { background: #f0fff4 !important; }
.comment-line { color: #888; font-style: italic; }

/* ── FULL CONFIG VIEW ────────────────────────── */
.full-cfg-view { /* starts hidden via inline style */ }
.full-cfg-legend { display: flex; flex-direction: column; gap: 6px;
                   padding: 10px 16px; font-size: 11px;
                   background: #f4f6f9; border-bottom: 1px solid #dde3ed; }
.full-cfg-legend-title { font-weight: 600; color: #444; margin-bottom: 2px; }
.leg { display: flex; align-items: flex-start; gap: 8px; line-height: 1.5; color: #333; }
.leg-swatch { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; margin-top: 2px; }
.leg-replaced { background: #ffe066; border: 1px solid #d4a900; }
.leg-added    { background: #d4f7dc; border: 1px solid #4caf6a; }
.leg-removed  { background: #ffd7d7; border: 1px solid #f55; }
.leg-equal    { background: #eef2f8; border: 1px solid #c8d0df; }
/* ── FILE SECTION FOOTER LEGEND ─────────────── */
.file-legend { display: flex; flex-wrap: wrap; gap: 14px; align-items: center;
               padding: 7px 14px; background: #f4f6f9;
               border-top: 1px solid #dde3ed; font-size: 11px; color: #555; }
.file-legend-label { font-weight: 600; color: #444; margin-right: 2px; }
.fleg { display: flex; align-items: center; gap: 5px; white-space: nowrap; }
.fleg-swatch { width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }
.fleg-replaced { background: #ffe066; border: 1px solid #d4a900; }
.fleg-added    { background: #d4f7dc; border: 1px solid #4caf6a; }
.fleg-removed  { background: #ffd7d7; border: 1px solid #f55; }
.fleg-error    { background: #ffebee; border: 1px solid #f55; }
.fleg-relonly  { background: #fff8f0; border: 1px solid #fd7e14; }
/* Two-column diff table: release on left, output on right */
.full-cfg-pre { font-family: 'Courier New', monospace; font-size: 12px;
                padding: 0; background: #fafbfc; line-height: 1.7; overflow-x: auto; }
.fcl-cols { display: grid; grid-template-columns: 1fr 1fr;
            border-top: 1px solid #eef0f4; min-width: 0; }
.fcl-cols:first-child { border-top: none; }
.fcl-cols:hover .fcl-cell { filter: brightness(0.97); }
.fcl-pane  { display: flex; min-width: 0; overflow: hidden; }
.fcl-pane.left { border-right: 2px solid #dde3ed; }
.fcl-lno  { flex-shrink: 0; width: 38px; padding: 0 6px; text-align: right;
            color: #aaa; border-right: 1px solid #dde3ed; background: #f0f2f6;
            user-select: none; font-size: 11px; line-height: 1.7; }
.fcl-cell { flex: 1; padding: 0 10px; white-space: pre-wrap; word-break: break-all;
            line-height: 1.7; min-width: 0; }
/* Equal rows */
.fcl-equal .fcl-cell  { background: #fff; }
.fcl-equal .fcl-lno   { background: #f0f2f6; }
/* Changed rows — release value replaced by base value in output */
.fcl-changed .fcl-cell { background: #fffbdd; }
.fcl-changed .fcl-lno  { background: #f5e97a; border-right-color: #d4a900; color: #7a6500; }
/* Added in output — base-only param inserted, not present in release */
.fcl-added .fcl-cell   { background: #eaffed; }
.fcl-added .fcl-lno    { background: #a6f0b0; border-right-color: #4caf6a; color: #1a6e32; }
.fcl-added .left .fcl-cell  { background: #f9fafc; color: #bbb; font-style: italic; }
.fcl-added .left .fcl-lno   { background: #f0f2f6; }
/* Removed from output — release param not carried through to output */
.fcl-removed .fcl-cell { background: #fff0f0; color: #c62828; text-decoration: line-through; }
.fcl-removed .fcl-lno  { background: #ffbbbb; border-right-color: #f55; color: #c62828; }
.fcl-removed .right .fcl-cell { background: #f9fafc; color: #bbb; font-style: italic;
                                 text-decoration: none; }
.fcl-removed .right .fcl-lno  { background: #f0f2f6; color: #aaa; }
/* Column headers */
.fcl-col-hdrs { display: grid; grid-template-columns: 1fr 1fr;
                font-size: 10px; font-weight: 600; color: #555;
                text-transform: uppercase; letter-spacing: .4px;
                background: #f0f2f6; border-bottom: 1px solid #dde3ed; }
.fcl-col-hdr  { padding: 5px 48px; }
.fcl-col-hdr.left { border-right: 2px solid #dde3ed; }

/* ── XML SYNTAX ──────────────────────────────── */
.xml-tag  { color: #0070c0; }
.xml-attr { color: #2e7d32; }
.xml-val  { color: #c62828; }
.xml-cmt  { color: #888; font-style: italic; }

/* ── JSON SYNTAX ─────────────────────────────── */
.jk  { color: #0070c0; }
.jvs { color: #2e7d32; }
.jvn { color: #e65100; }

/* ── FOOTER ──────────────────────────────────── */
footer { text-align: center; padding: 18px 18px 72px; font-size: 11px; color: #aaa; margin-top: 10px; }

/* ── STICKY LEGEND BAR ───────────────────────── */
/* Always visible at the bottom of the viewport — no scrolling needed */
.legend-bar { position: fixed; bottom: 0; left: 0; right: 0; z-index: 300;
              background: #1e2a3a; border-top: 2px solid #2d3f56;
              padding: 6px 16px; display: flex; flex-wrap: wrap;
              align-items: center; gap: 4px 16px; font-size: 11px; color: #cdd8e8; }
.legend-bar .lb-title { font-weight: 700; color: #fff; margin-right: 4px;
                        text-transform: uppercase; letter-spacing: .5px; font-size: 10px; }
.legend-bar .lb-sep   { width: 1px; height: 14px; background: #3a5070; flex-shrink: 0; }
.lb { display: flex; align-items: center; gap: 5px; white-space: nowrap;
      position: relative; cursor: default; }
.lb[data-tip]:hover::after {
  content: attr(data-tip);
  position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
  background: #0d1822; color: #e8f0fa; font-size: 11px; line-height: 1.5;
  padding: 7px 11px; border-radius: 5px; white-space: normal; width: 240px;
  box-shadow: 0 3px 10px rgba(0,0,0,.45); z-index: 400;
  border: 1px solid #2d3f56; pointer-events: none; }
.lb[data-tip]:hover::before {
  content: '';
  position: absolute; bottom: calc(100% + 2px); left: 50%; transform: translateX(-50%);
  border: 6px solid transparent; border-top-color: #2d3f56; z-index: 401; }
.lb-sw { width: 13px; height: 13px; border-radius: 3px; flex-shrink: 0; }
/* Change-row colours */
.lb-replaced { background: #ffe066; border: 1px solid #d4a900; }
.lb-base-only { background: #d4f7dc; border: 1px solid #4caf6a; }
.lb-rel-only  { background: #fff3e0; border: 1px solid #fd7e14; }
.lb-error     { background: #ffebee; border: 1px solid #f55; }
/* Full-config diff colours */
.lb-fc-changed  { background: #fffbdd; border: 1px solid #d4a900; }
.lb-fc-added    { background: #eaffed; border: 1px solid #4caf6a; }
.lb-fc-removed  { background: #fff0f0; border: 1px solid #f55; }
.lb-fc-equal    { background: #fff; border: 1px solid #c8d0df; }
"""


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS = """
/* ── Section toggle ───────────────────────────── */
function toggle(hdr) {
  hdr.closest('.file-section').classList.toggle('collapsed');
}

/* ── Expand / Collapse all ────────────────────── */
var _allCollapsed = false;
function toggleAll() {
  _allCollapsed = !_allCollapsed;
  document.querySelectorAll('.file-section').forEach(function(s) {
    s.classList.toggle('collapsed', _allCollapsed);
  });
  document.getElementById('expand-all-btn').textContent =
    _allCollapsed ? 'Expand All' : 'Collapse All';
}

/* ── Filter rows by change type ───────────────── */
function filterRows(type) {
  document.querySelectorAll('.toolbar button[data-filter]').forEach(function(b) {
    b.classList.remove('active');
  });
  event.target.classList.add('active');
  document.querySelectorAll('.change-row').forEach(function(r) {
    r.style.display = (!type || r.dataset.type === type) ? '' : 'none';
  });
}

/* ── Full config toggle ───────────────────────── */
function toggleFullConfig(btn, fileId) {
  var section = document.getElementById(fileId);
  if (!section) return;
  var changesView = section.querySelector('.changes-view');
  var fullView    = section.querySelector('.full-cfg-view');
  if (!fullView) return;
  /* Use computed style so the CSS-driven initial display:none is detected */
  var showingFull = window.getComputedStyle(fullView).display !== 'none';
  if (showingFull) {
    fullView.style.display    = 'none';
    changesView.style.display = '';
    btn.textContent = 'Show Full Config';
    btn.classList.remove('active');
  } else {
    fullView.style.display    = 'block';
    changesView.style.display = 'none';
    btn.textContent = 'Show Changes Only';
    btn.classList.add('active');
  }
}

/* ── Sidebar: select file ─────────────────────── */
function selectFile(fileId) {
  var section = document.getElementById(fileId);
  if (!section) return;
  section.classList.remove('collapsed');
  section.scrollIntoView({behavior: 'smooth', block: 'start'});
  document.querySelectorAll('.tree-file').forEach(function(el) {
    el.classList.remove('active');
  });
  var item = document.querySelector('.tree-file[data-fid="' + fileId + '"]');
  if (item) item.classList.add('active');
}

/* ── Sidebar: filter files by name ───────────── */
function filterSidebarFiles(val) {
  var q = val.toLowerCase();
  document.querySelectorAll('.tree-file').forEach(function(el) {
    el.style.display = (!q || el.dataset.name.toLowerCase().includes(q)) ? '' : 'none';
  });
}

/* ── Sidebar: toggle directory ────────────────── */
function toggleDir(id) {
  document.getElementById(id).classList.toggle('closed');
}
"""


# ---------------------------------------------------------------------------
# Syntax highlighting helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return html.escape(str(s))


def _highlight_xml(block: str, changed_values: Optional[List[str]] = None) -> str:
    def colorize(m: re.Match) -> str:
        text = m.group(0)
        if text.startswith("<!--"):
            return f'<span class="xml-cmt">{_esc(text)}</span>'
        text = re.sub(
            r'<(/?)(\w[\w-]*:?\w*)',
            lambda x: f'&lt;{x.group(1)}<span class="xml-tag">{_esc(x.group(2))}</span>',
            text,
        )
        text = re.sub(r'\b(\w[\w-]*)=', r'<span class="xml-attr">\1</span>=', text)
        text = re.sub(r'="([^"]*)"',
                      r'="<span class="xml-val">\1</span>"', text)
        return text

    colored = re.sub(r'<!--.*?-->|<[^>]+>', colorize, _esc(block), flags=re.DOTALL)
    if changed_values:
        for val in changed_values:
            ev = _esc(val)
            colored = colored.replace(ev, f'<span class="changed">{ev}</span>', 1)
    return colored


def _highlight_json(obj, changed_keys: Optional[List[str]] = None) -> str:
    try:
        if isinstance(obj, str):
            obj = json.loads(obj)
        lines = json.dumps(obj, indent=2).split("\n")
    except Exception:
        return _esc(str(obj))

    result = []
    for line in lines:
        m = re.match(r'^(\s*)"([^"]+)":\s*(.*)', line)
        if m:
            indent, key, rest = m.group(1), m.group(2), m.group(3)
            key_html = f'{indent}<span class="jk">"{_esc(key)}"</span>: '
            val_html  = _colour_json_value(rest, key, changed_keys)
            result.append(key_html + val_html)
        else:
            result.append(_esc(line))
    return "\n".join(result)


def _colour_json_value(val_str: str, key: str,
                       changed_keys: Optional[List[str]]) -> str:
    trailing = "," if val_str.endswith(",") else ""
    val_str   = val_str.rstrip(",")
    is_changed = changed_keys and key in changed_keys

    if val_str.startswith('"'):
        inner = val_str.strip('"')
        if is_changed:
            return (f'<span class="jvs">"<span class="changed">{_esc(inner)}'
                    f'</span>"</span>{trailing}')
        return f'<span class="jvs">"{_esc(inner)}"</span>{trailing}'
    try:
        float(val_str)
        if is_changed:
            return (f'<span class="jvn"><span class="changed">{_esc(val_str)}'
                    f'</span></span>{trailing}')
        return f'<span class="jvn">{_esc(val_str)}</span>{trailing}'
    except ValueError:
        pass
    return _esc(val_str) + trailing


# ---------------------------------------------------------------------------
# Full-config diff renderer  (base file ↔ merged output, line-level)
# ---------------------------------------------------------------------------

_FILE_FOOTER_LEGEND = (
    '<div class="file-legend">'
    '<span class="file-legend-label">Legend:</span>'
    '<span class="fleg"><span class="fleg-swatch fleg-replaced"></span>Value replaced by base</span>'
    '<span class="fleg"><span class="fleg-swatch fleg-added"></span>Added from base (not in release)</span>'
    '<span class="fleg"><span class="fleg-swatch fleg-removed"></span>In release, not carried to output</span>'
    '<span class="fleg"><span class="fleg-swatch fleg-error"></span>Error / Empty base override</span>'
    '<span class="fleg"><span class="fleg-swatch fleg-relonly"></span>Release-only (retained as-is)</span>'
    '</div>'
)

_LEGEND_HTML = (
    '<div class="full-cfg-legend">'
    '<span class="full-cfg-legend-title">Legend (Release ↔ Merged Output diff):</span>'
    '<div class="leg"><span class="leg-swatch leg-equal"></span>'
    '<span>Unchanged — same in release and merged output</span></div>'
    '<div class="leg"><span class="leg-swatch leg-replaced"></span>'
    '<span>Value replaced by base — release value overridden by base value in merged output</span></div>'
    '<div class="leg"><span class="leg-swatch leg-added"></span>'
    '<span>Added in output — present in base only, not in release (base-only parameter added)</span></div>'
    '<div class="leg"><span class="leg-swatch leg-removed"></span>'
    '<span>Removed from output — present in release but not carried to merged output</span></div>'
    '</div>'
)


def _render_full_config_diff(output_content: str, release_content: str) -> str:
    """
    Render a two-column diff: release file (left) vs merged output file (right).

    Colour coding on .fcl-cols rows:
      • fcl-equal   — identical in release and output
      • fcl-changed — line differs (release value replaced by base value in output)
      • fcl-added   — line only in output (base-only param added, absent in release)
      • fcl-removed — line only in release (not carried through to output)
    """
    release_lines = release_content.splitlines() if release_content else []
    output_lines  = output_content.splitlines()  if output_content  else []

    sm      = difflib.SequenceMatcher(None, release_lines, output_lines, autojunk=False)
    opcodes = sm.get_opcodes()

    col_hdrs = (
        '<div class="fcl-col-hdrs">'
        '<div class="fcl-col-hdr left">Release Config (before merge)</div>'
        '<div class="fcl-col-hdr right">Merged Output (after merge)</div>'
        '</div>'
    )

    rows: List[str] = []
    rel_lineno = 0
    out_lineno = 0

    def _pane(side: str, lineno: str, text: str) -> str:
        return (
            f'<div class="fcl-pane {side}">'
            f'<span class="fcl-lno">{lineno}</span>'
            f'<span class="fcl-cell">{_esc(text)}</span>'
            f'</div>'
        )

    def _blank_pane(side: str) -> str:
        return (
            f'<div class="fcl-pane {side}">'
            f'<span class="fcl-lno"></span>'
            f'<span class="fcl-cell"></span>'
            f'</div>'
        )

    def _cols_row(css: str, left_html: str, right_html: str) -> str:
        return f'<div class="fcl-cols {css}">{left_html}{right_html}</div>'

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for rel_line, out_line in zip(release_lines[i1:i2], output_lines[j1:j2]):
                rel_lineno += 1
                out_lineno += 1
                rows.append(_cols_row(
                    "fcl-equal",
                    _pane("left",  str(rel_lineno), rel_line),
                    _pane("right", str(out_lineno), out_line),
                ))

        elif tag == "replace":
            rel_chunk = release_lines[i1:i2]
            out_chunk = output_lines[j1:j2]
            n = max(len(rel_chunk), len(out_chunk))
            for k in range(n):
                if k < len(rel_chunk):
                    rel_lineno += 1
                    left_html = _pane("left", str(rel_lineno), rel_chunk[k])
                else:
                    left_html = _blank_pane("left")
                if k < len(out_chunk):
                    out_lineno += 1
                    right_html = _pane("right", str(out_lineno), out_chunk[k])
                else:
                    right_html = _blank_pane("right")
                rows.append(_cols_row("fcl-changed", left_html, right_html))

        elif tag == "insert":
            # Lines only in output — base-only param added (not in release)
            for out_line in output_lines[j1:j2]:
                out_lineno += 1
                rows.append(_cols_row(
                    "fcl-added",
                    _blank_pane("left"),
                    _pane("right", str(out_lineno), out_line),
                ))

        elif tag == "delete":
            # Lines only in release — not carried to merged output
            for rel_line in release_lines[i1:i2]:
                rel_lineno += 1
                rows.append(_cols_row(
                    "fcl-removed",
                    _pane("left", str(rel_lineno), rel_line),
                    _blank_pane("right"),
                ))

    return (
        col_hdrs +
        '<div class="full-cfg-pre">' +
        "".join(rows) +
        '</div>'
    )


# ---------------------------------------------------------------------------
# Per-change-type row builders  (unchanged from previous version)
# ---------------------------------------------------------------------------

def _tag_html(css_class: str, label: str) -> str:
    return f'<span class="tag {css_class}">{_esc(label)}</span>'


def _chg_header(param: str, tag_html: str, section: str = "",
                comment_badge: bool = False, extra: str = "") -> str:
    badges = '<span class="cbadge">comment changed</span>' if comment_badge else ""
    sect   = f'<span class="sect-label">§ {_esc(section)}</span>' if section else ""
    return (f'<div class="chg-hdr">'
            f'<span class="param-name">{_esc(param)}</span>'
            f'{tag_html}{sect}{badges}{extra}'
            f'</div>')


def _two_col_table(rel_content: str, mrg_content: str,
                   rel_header: str = "Release Config",
                   mrg_header: str = "Merged Config (from Base)",
                   row_class: str = "") -> str:
    return (
        f'<table class="diff-table">'
        f'<tr><th class="col-hdr rel">{_esc(rel_header)}</th>'
        f'<th class="col-hdr">{_esc(mrg_header)}</th></tr>'
        f'<tr class="{row_class}">'
        f'<td class="rel-col">{rel_content}</td>'
        f'<td class="mrg-col">{mrg_content}</td>'
        f'</tr></table>'
    )


def _render_kv_change(entry: ReportEntry) -> str:
    rel_comment   = entry.release_comment or ""
    base_comment  = entry.base_comment or ""
    comment_changed = rel_comment != base_comment and bool(rel_comment or base_comment)
    key = entry.element.split("|")[-1] if "|" in entry.element else entry.element

    rel_lines = ""
    mrg_lines = ""
    if rel_comment:
        rel_lines += f'<span class="comment-line">{_esc(rel_comment)}</span>\n'
        if comment_changed:
            rel_lines += '<span class="cbadge">release comment</span>\n'
    rel_lines += f'{_esc(key)}=<span class="changed">{_esc(entry.old)}</span>'

    if base_comment and comment_changed:
        mrg_lines += f'<span class="comment-line">{_esc(base_comment)}</span>\n'
        mrg_lines += '<span class="cbadge">base comment</span>\n'
    elif rel_comment:
        mrg_lines += f'<span class="comment-line">{_esc(rel_comment)}</span>\n'
    mrg_lines += f'{_esc(key)}=<span class="changed">{_esc(entry.new)}</span>'

    tag = _tag_html("replaced", "Base → Release Replaced")
    hdr = _chg_header(key, tag, entry.section, comment_changed)
    return hdr + _two_col_table(rel_lines, mrg_lines)


def _render_base_only(entry: ReportEntry) -> str:
    key = entry.element.split("|")[-1] if "|" in entry.element else entry.element
    comment_html = ""
    if entry.base_comment:
        comment_html = f'<span class="comment-line">{_esc(entry.base_comment)}</span>\n'
    mrg = comment_html + f'{_esc(key)}={_esc(entry.new)}'
    tag = _tag_html("base-only", "Base-Only Added")
    hdr = _chg_header(key, tag, entry.section)
    return hdr + _two_col_table(
        '<em style="color:#aaa;">(not present in release)</em>', mrg,
        row_class="added-row")


def _render_rel_only(entry: ReportEntry) -> str:
    key = entry.element.split("|")[-1] if "|" in entry.element else entry.element
    rel = f'{_esc(key)}={_esc(entry.old)}'
    mrg = rel + ' <em style="color:#888;">(no base entry — kept as-is)</em>'
    tag = _tag_html("rel-only", "Release-Only Retained")
    hdr = _chg_header(key, tag, entry.section)
    return hdr + _two_col_table(rel, mrg, row_class="relonly-row")


def _render_empty_override(entry: ReportEntry) -> str:
    key = entry.element.split("|")[-1] if "|" in entry.element else entry.element
    rel = f'{_esc(key)}=<span class="changed">{_esc(entry.old)}</span>'
    mrg = (f'{_esc(key)}= ⚠ <em style="color:#b71c1c;">base value is empty — '
           f'forced empty. Release value: {_esc(entry.recommended)}</em>')
    tag = _tag_html("error", "Empty Base Override")
    hdr = _chg_header(key, tag, entry.section)
    return hdr + _two_col_table(rel, mrg, row_class="error-row")


def _render_duplicate(entry: ReportEntry) -> str:
    rel = f'Duplicates found:\n{_esc(entry.old)}\n→ last value used: {_esc(entry.new)}'
    mrg = (f'{_esc(entry.element)}={_esc(entry.new)}\n'
           f'⚠ <em style="color:#b71c1c;">Duplicate key — review config</em>')
    tag = _tag_html("dup", "Duplicate Key")
    hdr = _chg_header(entry.element, tag)
    return hdr + _two_col_table(rel, mrg, row_class="error-row")


def _render_xml_change(entry: ReportEntry) -> str:
    element_id      = entry.element
    comment_changed = bool(entry.release_comment or entry.base_comment)
    rel_xml = _highlight_xml(entry.old)
    mrg_xml = _highlight_xml(entry.new)
    rel_content = rel_xml
    mrg_content = mrg_xml
    if entry.release_comment and comment_changed:
        rel_content = (f'<span class="xml-cmt">{_esc(entry.release_comment)}</span> '
                       f'<span class="cbadge">release comment</span>\n' + rel_xml)
    if entry.base_comment and comment_changed:
        mrg_content = (f'<span class="xml-cmt">{_esc(entry.base_comment)}</span> '
                       f'<span class="cbadge">base comment</span>\n' + mrg_xml)
    tag = _tag_html("replaced", "XML Base → Release Replaced")
    hdr = _chg_header(element_id, tag, comment_badge=comment_changed)
    return hdr + _two_col_table(rel_content, mrg_content)


def _render_json_change(entry: ReportEntry) -> str:
    element_id = entry.element
    try:
        rel_obj = json.loads(entry.old)
        mrg_obj = json.loads(entry.new)
    except Exception:
        rel_obj = entry.old
        mrg_obj = entry.new
    last_key = element_id.split(".")[-1] if "." in element_id else element_id
    rel_html = _highlight_json(rel_obj, [last_key])
    mrg_html = _highlight_json(mrg_obj, [last_key])
    tag = _tag_html("replaced", "JSON Base → Release Replaced")
    hdr = _chg_header(element_id, tag)
    return hdr + _two_col_table(rel_html, mrg_html)


def _render_namespace(entry: ReportEntry) -> str:
    rel = (f'<span class="xml-cmt">Release namespace (preserved in output):</span>\n'
           f'{_highlight_xml(entry.new)}')
    mrg = (f'<span class="xml-cmt">Base namespace (replaced — not leaked):</span>\n'
           f'{_highlight_xml(entry.old)}')
    tag = _tag_html("ns", "Namespace Retained")
    hdr = _chg_header("XML Namespace Header", tag)
    return hdr + _two_col_table(rel, mrg)


def _render_csv_union(entry: ReportEntry) -> str:
    key      = entry.element.split("|")[-1] if "|" in entry.element else entry.element
    base_vals = set(v.strip() for v in entry.new.split(","))
    rel_vals  = set(v.strip() for v in entry.old.split(","))
    added     = base_vals - rel_vals
    rel_content = f'{_esc(key)}=\n{_esc(entry.old)}'
    mrg_content = f'{_esc(key)}=\n'
    for v in entry.new.split(","):
        v = v.strip()
        if v in added:
            mrg_content += f'<span class="changed">{_esc(v)}</span>,'
        else:
            mrg_content += f'{_esc(v)},'
    mrg_content  = mrg_content.rstrip(",")
    mrg_content += (f'\n<em style="color:#888;font-size:11px;">'
                    f'↑ {len(added)} new entries from base</em>')
    tag = _tag_html("group", "CSV Union")
    hdr = _chg_header(key, tag, entry.section)
    return hdr + _two_col_table(rel_content, mrg_content)


def _render_group_appended(entry: ReportEntry) -> str:
    key = entry.element.split("|")[-1] if "|" in entry.element else entry.element
    rel = f'<em style="color:#aaa;">(new group from release: {_esc(entry.old)})</em>'
    mrg = f'Appended as: <span class="changed">{_esc(key)}</span> ({_esc(entry.new)})'
    tag = _tag_html("group", "Group Appended")
    hdr = _chg_header(key, tag, entry.section)
    return hdr + _two_col_table(rel, mrg, row_class="grp-add")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_TYPE_CSS = {
    EntryType.BASE_TO_RELEASE_REPLACED:           "replaced",
    EntryType.XML_BASE_TO_RELEASE_REPLACED:        "replaced",
    EntryType.JSON_BASE_TO_RELEASE_REPLACED:       "replaced",
    EntryType.LOGROTATE_BASE_TO_RELEASE_REPLACED:  "replaced",
    EntryType.BASE_ONLY_PARAMETER_ADDED:           "base-only",
    EntryType.RELEASE_ONLY_PARAMETER_ADDED:        "rel-only",
    EntryType.EMPTY_BASE_OVERRIDE:                 "error",
    EntryType.EMPTY_BASE_OVERRIDE_XML:             "error",
    EntryType.JSON_EMPTY_BASE_OVERRIDE:            "error",
    EntryType.LOGROTATE_EMPTY_BASE_OVERRIDE:       "error",
    EntryType.DUPLICATE_KEY:                       "dup",
    EntryType.INDEXED_GROUP_APPENDED:              "group",
    EntryType.COMMA_VALUE_UNION:                   "group",
    EntryType.NAMESPACE_ADAPTED:                   "ns",
}


def _render_entry(entry: ReportEntry) -> str:
    t = entry.type
    if t == EntryType.BASE_TO_RELEASE_REPLACED:          return _render_kv_change(entry)
    if t == EntryType.BASE_ONLY_PARAMETER_ADDED:         return _render_base_only(entry)
    if t == EntryType.RELEASE_ONLY_PARAMETER_ADDED:      return _render_rel_only(entry)
    if t in (EntryType.EMPTY_BASE_OVERRIDE, EntryType.EMPTY_BASE_OVERRIDE_XML,
             EntryType.JSON_EMPTY_BASE_OVERRIDE,
             EntryType.LOGROTATE_EMPTY_BASE_OVERRIDE):   return _render_empty_override(entry)
    if t == EntryType.DUPLICATE_KEY:                     return _render_duplicate(entry)
    if t == EntryType.XML_BASE_TO_RELEASE_REPLACED:      return _render_xml_change(entry)
    if t == EntryType.JSON_BASE_TO_RELEASE_REPLACED:     return _render_json_change(entry)
    if t == EntryType.NAMESPACE_ADAPTED:                 return _render_namespace(entry)
    if t == EntryType.COMMA_VALUE_UNION:                 return _render_csv_union(entry)
    if t == EntryType.INDEXED_GROUP_APPENDED:            return _render_group_appended(entry)
    # Generic fallback
    tag = _tag_html(_TYPE_CSS.get(t, "replaced"), t.replace("_", " ").title())
    hdr = _chg_header(entry.element, tag)
    return hdr + _two_col_table(_esc(entry.old), _esc(entry.new))


# ---------------------------------------------------------------------------
# Summary bar
# ---------------------------------------------------------------------------

def _summary_html(results: List[MergeResult]) -> str:
    from collections import defaultdict as _dd
    counts = _dd(int)
    total_files = set()
    for r in results:
        for e in r.report:
            counts[e.type] += 1
            total_files.add(f"{r.base_name}/{e.file}")

    replaced = (counts[EntryType.BASE_TO_RELEASE_REPLACED] +
                counts[EntryType.XML_BASE_TO_RELEASE_REPLACED] +
                counts[EntryType.JSON_BASE_TO_RELEASE_REPLACED] +
                counts[EntryType.LOGROTATE_BASE_TO_RELEASE_REPLACED])
    errors   = sum(counts[t] for t in EntryType.CRITICAL_TYPES)
    dups     = counts[EntryType.DUPLICATE_KEY]

    def stat(num, label, err=False):
        cls = "stat err" if err else "stat"
        return (f'<div class="{cls}"><span class="num">{num}</span>'
                f'<span class="lbl">{label}</span></div>')

    total_changes = sum(len(r.report) for r in results)
    return (
        f'<div class="summary">'
        f'{stat(len(total_files), "Files Changed")}'
        f'<div class="stat-div"></div>'
        f'{stat(total_changes, "Total Changes")}'
        f'<div class="stat-div"></div>'
        f'{stat(replaced, "Replaced")}'
        f'{stat(counts[EntryType.BASE_ONLY_PARAMETER_ADDED], "Base-Only Added")}'
        f'{stat(counts[EntryType.RELEASE_ONLY_PARAMETER_ADDED], "Release-Only")}'
        f'<div class="stat-div"></div>'
        f'{stat(errors, "Errors", err=True)}'
        f'{stat(dups, "Duplicates", err=True)}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _strip_release_prefix(file_path: str, release_dirs: List[str]) -> str:
    """Strip the leading release-dir component from a file path for display."""
    norm = file_path.replace("\\", "/")
    for rd in release_dirs:
        prefix = os.path.basename(os.path.normpath(rd)).rstrip("/") + "/"
        if norm.startswith(prefix):
            return norm[len(prefix):]
    # fallback: strip first path component
    parts = norm.split("/", 1)
    return parts[1] if len(parts) > 1 else norm


def _insert_into_tree(tree: dict, parts: list, fid: str, badge: int) -> None:
    """Recursively insert a file path into a tree dict.

    Leaf nodes:  {"__fid__": str, "__badge__": int}
    Dir  nodes:  {child_name: ..., ...}
    """
    if len(parts) == 1:
        tree[parts[0]] = {"__fid__": fid, "__badge__": badge}
    else:
        key = parts[0]
        if key not in tree or "__fid__" in tree.get(key, {}):
            tree[key] = {}
        _insert_into_tree(tree[key], parts[1:], fid, badge)


def _render_tree_nodes(node: dict, depth: int, id_counter: List[int]) -> str:
    """Recursively render a tree dict as nested HTML directory/file nodes."""
    dirs  = sorted(
        (k, v) for k, v in node.items()
        if isinstance(v, dict) and "__fid__" not in v
    )
    files = sorted(
        (k, v) for k, v in node.items()
        if isinstance(v, dict) and "__fid__" in v
    )

    parts = []
    pad_dir  = depth * 14          # px indent for directory headers
    pad_file = (depth + 1) * 14    # px indent for file entries

    for name, child in dirs:
        id_counter[0] += 1
        did   = f"td{id_counter[0]}"
        inner = _render_tree_nodes(child, depth + 1, id_counter)
        parts.append(
            f'<div class="tree-dir" id="{did}">'
            f'<div class="tree-dir-hdr" style="padding:4px 8px 4px {pad_dir+6}px" '
            f'onclick="toggleDir(\'{did}\')">'
            f'<span class="tree-chevron">&#9660;</span>'
            f'{_esc(name)}/'
            f'</div>'
            f'<div class="tree-dir-body">{inner}</div>'
            f'</div>'
        )

    for name, child in files:
        fid   = child["__fid__"]
        badge = child["__badge__"]
        parts.append(
            f'<div class="tree-file" data-fid="{fid}" data-name="{_esc(name)}" '
            f'style="padding:4px 8px 4px {pad_file}px" '
            f'onclick="selectFile(\'{fid}\')" title="{_esc(name)}">'
            f'<span class="fn">{_esc(name)}</span>'
            f'<span class="sbadge">{badge}</span>'
            f'</div>'
        )

    return "".join(parts)


def _sidebar_html(
    results: List[MergeResult],
    file_ids: Dict[str, str],    # "base_name/entry.file" → html-id
    release_dirs: List[str],
    output_dir: str = "output",
) -> str:
    """Render a collapsible file-system tree in the left sidebar."""
    multi       = len(results) > 1
    id_counter  = [0]
    out_name    = os.path.basename(os.path.normpath(output_dir)) or "output"

    # Build per-result trees
    result_trees: List[tuple] = []   # (display_name, tree_dict)
    for result in results:
        n_per_file: Dict[str, int] = {}
        for e in result.report:
            n_per_file[e.file] = n_per_file.get(e.file, 0) + 1

        tree: dict = {}
        for fname, n in n_per_file.items():
            fid = file_ids.get(f"{result.base_name}/{fname}", "")
            if not fid:
                continue
            display = _strip_release_prefix(fname, release_dirs)
            path_parts = display.replace("\\", "/").split("/")
            _insert_into_tree(tree, path_parts, fid, n)

        label = result.base_name or out_name
        result_trees.append((label, tree))

    # Render inner content (base-name dirs for multi, flat tree for single)
    inner_html = ""
    for label, tree in result_trees:
        if multi:
            # base-name node is depth=1 child of output/:  1*14+6 = 20px indent
            # its content (config/, hadoop/, …) starts at depth=2
            id_counter[0] += 1
            did   = f"td{id_counter[0]}"
            inner = _render_tree_nodes(tree, 2, id_counter)
            inner_html += (
                f'<div class="tree-dir" id="{did}">'
                f'<div class="tree-dir-hdr" style="padding:4px 8px 4px 20px" '
                f'onclick="toggleDir(\'{did}\')">'
                f'<span class="tree-chevron">&#9660;</span>'
                f'{_esc(label)}/'
                f'</div>'
                f'<div class="tree-dir-body">{inner}</div>'
                f'</div>'
            )
        else:
            # single-base: content is depth=1 child of output/:  dirs at 1*14+6=20px
            inner_html += _render_tree_nodes(tree, 1, id_counter)

    # Wrap everything under the output/ root node
    id_counter[0] += 1
    root_id = f"td{id_counter[0]}"
    tree_html = (
        f'<div class="tree-root">'
        f'<div class="tree-dir" id="{root_id}">'
        f'<div class="tree-dir-hdr" style="padding:5px 8px 5px 6px" '
        f'onclick="toggleDir(\'{root_id}\')">'
        f'<span class="tree-chevron">&#9660;</span>'
        f'{_esc(out_name)}/'
        f'</div>'
        f'<div class="tree-dir-body">{inner_html}</div>'
        f'</div>'
        f'</div>'
    )

    return (
        f'<div class="sidebar">'
        f'<div class="sidebar-title">Files</div>'
        f'<div class="sidebar-search">'
        f'<input type="text" placeholder="Filter files&#8230;" '
        f'oninput="filterSidebarFiles(this.value)"></div>'
        f'{tree_html}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def write_html(
    results: List[MergeResult],
    config: MergeConfig,
    report_dir: str = "reports",
) -> Path:
    """
    Generate a single combined HTML report for all base-dir merge passes.

    results   — list of MergeResult, one per BaseDirConfig
    config    — top-level MergeConfig (for release_dirs / output_dir metadata)
    report_dir — directory to write the HTML file into
    """
    if not results:
        results = []

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    multi   = len(results) > 1

    # ── Page header ──────────────────────────────────────────────────────
    bases_str = _esc(", ".join(r.base_dir or r.base_name for r in results))
    rel_str   = _esc(", ".join(config.release_dirs))
    out_str   = _esc(config.output_dir)
    header_html = (
        f'<div class="page-header">'
        f'<h1>ConfigMergeTool &#8212; Merge Diff Report</h1>'
        f'<div class="meta">'
        f'<span><label>Base(s):</label>{bases_str}</span>'
        f'<span><label>Release:</label>{rel_str}</span>'
        f'<span><label>Output:</label>{out_str}</span>'
        f'<span><label>Generated:</label>{now_str}</span>'
        f'</div></div>'
    )

    summary_html = _summary_html(results)

    # ── Build file sections + collect IDs ────────────────────────────────
    #    ID scheme: "f{global_counter}" across all results
    file_ids: Dict[str, str] = {}   # "base_name/rel_path" → html-id
    global_fnum = 0

    sections_html_parts: List[str] = []
    for result in results:
        by_file: Dict[str, List[ReportEntry]] = defaultdict(list)
        for entry in result.report:
            by_file[entry.file].append(entry)

        for fname, entries in by_file.items():
            global_fnum += 1
            fid         = f"f{global_fnum}"
            composite   = f"{result.base_name}/{fname}"
            file_ids[composite] = fid

            n_changes   = len(entries)
            out_content     = result.output_contents.get(fname, "")
            release_content = result.release_contents.get(fname, "")
            has_content     = bool(out_content)

            # ── Full-config diff view (release ↔ output) ──────────────────
            full_cfg_html = ""
            if has_content:
                diff_body = _render_full_config_diff(out_content, release_content)
                full_cfg_html = (
                    f'<div class="full-cfg-view" style="display:none">'
                    f'{diff_body}'
                    f'</div>'
                )

            # ── Changes view ──────────────────────────────────────────────
            rows_html = ""
            for ridx, entry in enumerate(entries):
                row_body  = _render_entry(entry)
                first_cls = " first" if ridx == 0 else ""
                rows_html += (
                    f'<div class="change-row{first_cls}" data-type="{entry.type}">'
                    f'{row_body}</div>'
                )
            view_label = (
                "Showing changed parameters only — click "
                "<b>Show Full Config</b> to see the complete merged file with diff highlights"
                if has_content else
                "Showing changed parameters only"
            )
            changes_view = (
                f'<div class="changes-view">'
                f'<div class="view-label">{view_label}</div>'
                f'{rows_html}'
                f'</div>'
            )

            # ── File header ───────────────────────────────────────────────
            base_tag_html = ""
            if multi:
                base_tag_html = (
                    f'<span class="base-tag">{_esc(result.base_name)}</span>'
                )
            toggle_btn = ""
            if has_content:
                toggle_btn = (
                    f'<button class="full-cfg-btn" '
                    f'onclick="event.stopPropagation(); toggleFullConfig(this, \'{fid}\')">'
                    f'Show Full Config</button>'
                )

            sections_html_parts.append(
                f'<div class="file-section" id="{fid}">'
                f'<div class="file-hdr" onclick="toggle(this)">'
                f'<span class="chevron">&#9660;</span>'
                f'<span class="fname">{_esc(fname)}</span>'
                f'{base_tag_html}'
                f'<span class="badge">{n_changes} change{"s" if n_changes != 1 else ""}</span>'
                f'{toggle_btn}'
                f'</div>'
                f'<div class="file-body">{changes_view}{full_cfg_html}</div>'
                f'</div>'
            )

    sections_html = "\n".join(sections_html_parts)

    # ── Sidebar (built after IDs are known) ──────────────────────────────
    sidebar_html = _sidebar_html(results, file_ids, config.release_dirs, config.output_dir)

    # ── Toolbar ──────────────────────────────────────────────────────────
    toolbar_html = (
        '<div class="toolbar">'
        '<button class="active" data-filter="" onclick="filterRows(null)">All Changes</button>'
        f'<button data-filter="{EntryType.EMPTY_BASE_OVERRIDE}" '
        f'onclick="filterRows(\'{EntryType.EMPTY_BASE_OVERRIDE}\')">Errors Only</button>'
        f'<button data-filter="{EntryType.BASE_ONLY_PARAMETER_ADDED}" '
        f'onclick="filterRows(\'{EntryType.BASE_ONLY_PARAMETER_ADDED}\')">Base-Only Added</button>'
        f'<button data-filter="{EntryType.RELEASE_ONLY_PARAMETER_ADDED}" '
        f'onclick="filterRows(\'{EntryType.RELEASE_ONLY_PARAMETER_ADDED}\')">Release-Only</button>'
        '<div class="spacer"></div>'
        '<button id="expand-all-btn" onclick="toggleAll()">Collapse All</button>'
        '</div>'
    )

    footer_html = (
        f'<footer>Generated by ConfigMergeTool &mdash; {now_str}</footer>'
    )

    legend_bar_html = (
        '<div class="legend-bar">'
        '<span class="lb-title">Legend</span>'
        '<span class="lb" data-tip="Release value overridden by base value in merged output.">'
          '<span class="lb-sw lb-replaced"></span>Value replaced by base</span>'
        '<span class="lb" data-tip="Parameter present in base only, not in release — added to merged output.">'
          '<span class="lb-sw lb-base-only"></span>Added from base</span>'
        '<span class="lb" data-tip="Parameter present in release only, not in base — retained as-is in merged output.">'
          '<span class="lb-sw lb-rel-only"></span>Release-only</span>'
        '<span class="lb" data-tip="Base value is empty so release value was used — review recommended.">'
          '<span class="lb-sw lb-error"></span>Error / Empty override</span>'
        '<span class="lb-sep"></span>'
        '<span class="lb-title">Full Config Diff</span>'
        '<span class="lb" data-tip="Same in release and merged output — no change.">'
          '<span class="lb-sw lb-fc-equal"></span>Unchanged</span>'
        '<span class="lb" data-tip="Line exists in both; release value was replaced by base value in merged output.">'
          '<span class="lb-sw lb-fc-changed"></span>Value replaced</span>'
        '<span class="lb" data-tip="Present in base only, not in release — added to merged output.">'
          '<span class="lb-sw lb-fc-added"></span>Added in output</span>'
        '<span class="lb" data-tip="Present in release but not carried through to merged output.">'
          '<span class="lb-sw lb-fc-removed"></span>In release only</span>'
        '</div>'
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ConfigMergeTool &#8212; Merge Diff Report</title>
<style>{_CSS}</style>
</head>
<body>
{header_html}
{summary_html}
<div class="layout">
{sidebar_html}
<div class="main">
{toolbar_html}
{sections_html}
{footer_html}
</div>
</div>
{legend_bar_html}
<script>{_JS}</script>
</body>
</html>"""

    Path(report_dir).mkdir(parents=True, exist_ok=True)
    # Directory carries the run timestamp; keep the filename simple.
    report_path = Path(report_dir) / "merge_diff.html"
    report_path.write_text(page, encoding="utf-8")
    return report_path
