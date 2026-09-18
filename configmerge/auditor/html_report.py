"""
configmerge.auditor.html_report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generate a self-contained interactive HTML audit report.

QE fixes applied:
  BUG-05: applyOverride clears pending if new value equals original
  BUG-06: sidebar badges refresh after every state change
  BUG-07: filterFiles hides empty directory headers
  BUG-08: text/xml renderParamTable given unique table id
  MISS-02: "Export Patch" button downloads audit_patch.json
  MISS-03: Change Log panel tracks every pending change in real time

Output: <run_dir>/audit_report.html
"""

from __future__ import annotations

import html.parser as _html_parser
import json
import os
import re
import sys
from typing import TYPE_CHECKING
from urllib.parse import quote as _url_quote

if TYPE_CHECKING:
    from .engine import AuditResult


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;background:#f4f6f9;color:#222;
     display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* ── TOP BAR ── */
.page-header{background:#1e2a3a;color:#fff;padding:11px 22px;position:sticky;top:0;z-index:200;
             display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.header-title{flex:1;min-width:0}
.page-header h1{font-size:16px;font-weight:600;margin-bottom:2px}
.page-header .meta{font-size:11px;color:#9ab;display:flex;gap:14px;flex-wrap:wrap}
.page-header .meta label{color:#6a8fa8;margin-right:3px}
.header-actions{display:flex;gap:6px;flex-shrink:0}
.hdr-btn{background:#2e3d52;color:#cde;border:1px solid #3d5068;border-radius:4px;
         padding:5px 10px;font-size:11px;cursor:pointer;white-space:nowrap}
.hdr-btn:hover{background:#3d5068}
.hdr-btn.accent{background:#1565c0;border-color:#1976d2;color:#fff}
.hdr-btn.accent:hover{background:#0d47a1}
.change-counter{background:#c62828;color:#fff;border-radius:10px;
                padding:1px 7px;font-size:11px;margin-left:4px;display:none}
.change-counter.has-changes{display:inline}

/* ── SUMMARY BAR ── */
.summary{background:#fff;border-bottom:1px solid #dde3ed;padding:8px 22px;
         display:flex;gap:16px;flex-wrap:wrap;align-items:center;flex-shrink:0}
.summary-row{display:flex;gap:16px;flex-wrap:wrap;align-items:center;width:100%}
.summary-sub{font-size:10px;color:#888;background:#f8fafc;border-top:1px solid #eef0f4;
             padding:3px 22px 4px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;flex-shrink:0}
.summary-sub .lbl{color:#aaa;font-weight:600;margin-right:4px}
.stat{display:flex;flex-direction:column;align-items:center;min-width:64px}
.stat .num{font-size:19px;font-weight:700;color:#1e2a3a}
.stat .lbl{font-size:10px;color:#777;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}
.stat.err .num{color:#c62828}
.stat.warn .num{color:#e65100}
.stat-div{width:1px;background:#dde3ed;align-self:stretch}

/* ── LAYOUT ── */
.layout{display:flex;flex:1;min-height:0;overflow:hidden}
.sidebar{width:270px;flex-shrink:0;
         background:#fff;border-right:1px solid #dde3ed;
         display:flex;flex-direction:column;overflow:hidden;
         /* height derived from flex parent — do not use height:100% (unreliable) */
         align-self:stretch}
.sidebar-files{flex:1;overflow-y:auto}
.main{flex:1;min-width:0;overflow-y:auto;overflow-x:auto}

/* ── SIDEBAR ── */
.sidebar-title{padding:7px 12px 5px;font-size:11px;font-weight:700;color:#1e2a3a;
               text-transform:uppercase;letter-spacing:.6px;border-bottom:1px solid #eef0f4;
               flex-shrink:0;display:flex;align-items:center;gap:6px}
.sidebar-title-text{flex:1}
.diffs-only-toggle{background:none;border:1px solid #c0c8d8;border-radius:10px;
                   padding:2px 8px;font-size:10px;cursor:pointer;color:#555;
                   white-space:nowrap;font-weight:400;text-transform:none;letter-spacing:0}
.diffs-only-toggle.active{background:#c62828;color:#fff;border-color:#c62828}
.diffs-only-toggle:hover{border-color:#1e2a3a}
.sidebar-search{padding:5px 9px 6px;border-bottom:1px solid #eef0f4;flex-shrink:0}
.sidebar-search input{width:100%;padding:4px 24px 4px 8px;border:1px solid #c0c8d8;
                       border-radius:4px;font-size:12px;background:#f9fafc}
.sidebar-search input:focus{outline:none;border-color:#1565c0;background:#fff}

/* ── DIFF-FILES QUICK LIST ── */
.diff-quicklist{flex-shrink:0;border-bottom:2px solid #ffcdd2;background:#fff8f8;max-height:200px;overflow-y:auto}
.diff-quicklist-hdr{display:flex;align-items:center;gap:5px;padding:6px 10px;
                    cursor:pointer;font-size:11px;color:#c62828;font-weight:700;
                    background:#ffebee;user-select:none;position:sticky;top:0;z-index:2}
.diff-quicklist-hdr:hover{background:#ffcdd2}
.diff-qfile{display:flex;align-items:center;gap:5px;padding:4px 10px 4px 16px;
            cursor:pointer;font-size:11px;color:#b71c1c;border-left:3px solid #ef9a9a}
.diff-qfile:hover{background:#ffebee}
.diff-qfile .diff-qbadge{background:#c62828;color:#fff;font-size:9px;border-radius:6px;
                          padding:0 5px;flex-shrink:0;margin-left:auto}
.diff-qfile .diff-qname{font-family:monospace;font-size:11px;white-space:nowrap;
                         overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}

/* ── TREE SIDEBAR ── */
.tree-dir{border-bottom:1px solid #f0f2f6}
.tree-dir-hdr{display:flex;align-items:center;gap:4px;padding:5px 8px;
              cursor:pointer;font-size:12px;color:#1e2a3a;font-weight:600;
              background:#f8fafc;user-select:none;position:relative}
.tree-dir-hdr:hover{background:#eef2f8}
.tree-dir-hdr .dir-chev{font-size:9px;color:#999;flex-shrink:0}
.tree-dir-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dir-diff-badge{background:#c62828;color:#fff;font-size:9px;border-radius:6px;
                padding:1px 5px;flex-shrink:0;margin-left:2px}
.dir-ok-badge{background:#388e3c;color:#fff;font-size:9px;border-radius:6px;
              padding:1px 5px;flex-shrink:0;margin-left:2px}
.dir-missing-badge{background:#e65100;color:#fff;font-size:9px;border-radius:6px;
                   padding:1px 5px;flex-shrink:0;margin-left:2px}
.tree-file{display:flex;align-items:center;justify-content:space-between;
           padding:4px 8px 4px 0;cursor:pointer;font-size:12px;color:#444;
           border-left:3px solid transparent}
.tree-file:hover{background:#f0f4fb}
.tree-file.active{background:#e8eef8;border-left-color:#1e2a3a;color:#1e2a3a;font-weight:600}
.tree-file-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-left:4px}
.mismatch-badge{background:#c62828;color:#fff;font-size:10px;border-radius:8px;
                padding:1px 6px;flex-shrink:0;margin-left:4px}
.missing-file-badge{background:#e65100;color:#fff;font-size:10px;border-radius:8px;
                    padding:1px 6px;flex-shrink:0;margin-left:4px}
.ok-badge{background:#388e3c;color:#fff;font-size:10px;border-radius:8px;
          padding:1px 6px;flex-shrink:0;margin-left:4px}
.pending-badge{background:#1565c0;color:#fff;font-size:10px;border-radius:8px;
               padding:1px 6px;flex-shrink:0;margin-left:4px}

/* ── WARNING BANNER ── */
.warn-banner{background:#fff3e0;border-left:4px solid #f57c00;padding:6px 14px;
             font-size:11px;color:#bf360c;margin:0}

/* ── MATCH BANNER ── */
.match-banner{background:#e8f5e9;border-left:4px solid #388e3c;padding:10px 20px;
              font-size:12px;color:#1b5e20;display:flex;align-items:center;gap:8px}
.match-banner .match-icon{font-size:18px}

/* ── CONTENT-SKIPPED BANNER (large identical files) ── */
.skip-banner{background:#f1f8e9;border:1px solid #aed581;border-radius:6px;
             margin:20px;padding:18px 22px;display:flex;align-items:flex-start;gap:16px}
.skip-banner-icon{font-size:28px;line-height:1;flex-shrink:0}
.skip-banner-body{flex:1;min-width:0}
.skip-banner-title{font-size:14px;font-weight:700;color:#33691e;margin-bottom:6px}
.skip-banner-note{font-size:12px;color:#558b2f;margin-bottom:10px}
.skip-banner-sizes{display:flex;flex-wrap:wrap;gap:10px}
.skip-size-chip{background:#dcedc8;color:#33691e;border-radius:4px;
                padding:3px 10px;font-size:11px;font-family:monospace}

/* ── LOGICAL DIFF ── */
.logical-diff-row td{background:#f3e5f5}
.logical-diff-row:hover td{background:#e1bee7}
.logical-badge{background:#7b1fa2;color:#fff;font-size:10px;border-radius:8px;
               padding:1px 6px;flex-shrink:0;margin-left:4px}
.logical-lbl{color:#7b1fa2;font-size:10px;font-style:italic;display:block;margin-top:2px}
.cell-logical .val-display{color:#6a1b9a}
.logical-tag{background:#f3e5f5;color:#7b1fa2;border-radius:3px;padding:1px 7px;font-size:11px}

/* ── MAIN PANEL ── */
.panel-file-hdr{background:#eef2f8;padding:12px 20px;border-bottom:1px solid #dde3ed}
.panel-file-path{font-weight:700;font-size:14px;color:#1e2a3a;margin-bottom:4px;font-family:monospace}
.panel-file-meta{font-size:11px;color:#666;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.node-tag{background:#e8f4fd;color:#1565c0;border-radius:3px;padding:1px 7px;font-size:11px}
.absent-tag{background:#fff3e0;color:#e65100;border-radius:3px;padding:1px 7px;font-size:11px}

/* ── PANEL FILE HEADER + TOOLBAR (sticky within .main scroll context) ── */
.panel-sticky-hdr{position:sticky;top:0;z-index:20;background:#fff;
                  box-shadow:0 2px 6px rgba(0,0,0,.08)}

/* ── TOOLBAR ── */
.panel-toolbar{display:flex;align-items:center;gap:10px;padding:7px 20px;
               background:#fff;border-bottom:1px solid #eef0f4;flex-wrap:wrap}
.panel-toolbar label{font-size:12px;display:flex;align-items:center;gap:5px;cursor:pointer}
.dl-group{margin-left:auto;display:flex;gap:6px}
.dl-btn{background:#1e2a3a;color:#fff;border:none;border-radius:4px;
        padding:5px 11px;font-size:12px;cursor:pointer}
.dl-btn:hover{background:#2e3d52}

/* ── TAB NAVIGATION ── */
.tab-bar{display:flex;gap:0;background:#fff;border-bottom:2px solid #dde3ed;flex-shrink:0}
.tab-btn{padding:7px 18px;font-size:12px;font-weight:600;color:#666;border:none;
         background:none;cursor:pointer;border-bottom:3px solid transparent;
         margin-bottom:-2px;white-space:nowrap;transition:color .15s,border-color .15s}
.tab-btn:hover{color:#1e2a3a;background:#f4f6f9}
.tab-btn.active{color:#1565c0;border-bottom-color:#1565c0;background:#fff}
.tab-count{background:#e0e6f0;color:#555;border-radius:9px;padding:1px 7px;
           font-size:10px;margin-left:5px;font-weight:400}
.tab-count.has-items{background:#c62828;color:#fff}
.tab-panel{display:none;flex:1;min-height:0;overflow:hidden;flex-direction:column}
.tab-panel.active{display:flex}
/* Full-page tab panels (skipped / filtered) */
.tab-fullpage{flex:1;overflow-y:auto;padding:20px}
.tab-fullpage-hdr{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.tab-fullpage-title{font-size:15px;font-weight:700;color:#1e2a3a}
.tab-back-btn{background:#f0f2f6;border:1px solid #c0c8d8;border-radius:4px;
              padding:4px 12px;font-size:11px;cursor:pointer;color:#1e2a3a}
.tab-back-btn:hover{background:#dde3ed}
.tab-section-hdr{font-size:12px;font-weight:700;color:#555;text-transform:uppercase;
                 letter-spacing:.4px;padding:8px 0 6px;margin-top:12px;
                 border-bottom:1px solid #dde3ed;margin-bottom:8px}
.tab-empty{padding:40px 20px;text-align:center;color:#999;font-size:13px}

/* ── AUDIT TABLE ── */
/* Phase 3.0: horizontal scroll + sticky parameter column for many-node audits */
.table-wrap{padding:0 0 60px}
.audit-table{width:max-content;min-width:100%;border-collapse:collapse;table-layout:fixed}
.audit-table thead{position:sticky;top:0;z-index:10}
.audit-table th{background:#1e2a3a;color:#fff;padding:8px 10px;text-align:left;
                font-size:12px;font-weight:600;border-right:1px solid #2e3d52}
.audit-table th:last-child{border-right:none}
/* Sticky parameter column */
.key-th{width:220px;position:sticky;left:0;z-index:12;background:#1e2a3a}
.val-th{min-width:180px}
.absent-node-hdr{background:#3a2a1e;color:#c9a97a}
.node-dir{font-size:10px;color:#9ab;font-weight:400;display:block;margin-top:2px}

/* Node visibility chip selector (shown when nodes > 4) */
.node-selector{display:flex;gap:6px;flex-wrap:wrap;align-items:center;
               padding:8px 20px;border-bottom:1px solid #eef0f4;background:#fff}
.node-sel-label{font-size:11px;color:#666;font-weight:600}
.node-chip{background:#e8eef8;color:#1e2a3a;border:1px solid #c0c8d8;
           border-radius:12px;padding:3px 10px;font-size:11px;cursor:pointer}
.node-chip.active{background:#1565c0;color:#fff;border-color:#1565c0}
.node-chip:hover{opacity:.85}
.node-sel-all,.node-sel-none{background:none;border:1px solid #aaa;border-radius:4px;
                              padding:3px 8px;font-size:11px;cursor:pointer;color:#555}

.section-divider td{background:#f0f2f6;font-size:11px;font-weight:700;color:#555;
                     padding:5px 10px;letter-spacing:.3px;text-transform:uppercase;
                     border-top:2px solid #dde3ed;position:relative;z-index:0}
.section-divider-controls{float:right;display:flex;gap:4px}
.sec-skip-btn{background:#607d8b;color:#fff;border:none;border-radius:3px;
              padding:2px 7px;font-size:10px;cursor:pointer;text-transform:none;letter-spacing:0}
.sec-skip-btn:hover{background:#455a64}
.sec-addfrom-btn{background:#1565c0;color:#fff;border:none;border-radius:3px;
                 padding:2px 7px;font-size:10px;cursor:pointer;text-transform:none;letter-spacing:0}
.sec-addfrom-btn:hover{background:#0d47a1}
/* Section check (KV): base param count and per-node match/differ/missing/extra */
.sec-chk{display:flex;flex-wrap:wrap;gap:3px 14px;margin-top:3px;text-transform:none;
         letter-spacing:0;font-weight:400;font-size:11px}
.sec-chk-base{color:#1e2a3a;font-weight:600}
.sec-chk-ok{color:#2e7d32}
.sec-chk-bad{color:#b71c1c}
.sec-chk-absent{color:#e65100;font-style:italic}
/* Duplicate in section: every active value with its source line */
.dup-val{font-family:monospace}
.dup-line{color:#888;font-size:10px}
.dup-tag{display:inline-block;margin-top:2px;font-size:10px;color:#fff;background:#e65100;
         border-radius:3px;padding:0 5px}
.param-row td{border-bottom:1px solid #eef0f4;padding:0;vertical-align:top}
.param-row:hover td{background:#fafbfc}
.mismatch-row td{background:#fffde7}
.mismatch-row:hover td{background:#fff9c4}
.has-pending td{background:#e3f2fd}
.has-pending:hover td{background:#bbdefb}
.logical-diff-row td{background:#f3e5f5}
.logical-diff-row:hover td{background:#e1bee7}

/* Sticky key cell — must match row background explicitly (inherit fails on transparent layers) */
.key-cell{padding:8px 10px;font-family:monospace;font-size:12px;
          color:#1e2a3a;border-right:2px solid #c0c8d8;
          position:sticky;left:0;z-index:5;background:#fff}
.param-row:hover         .key-cell{background:#fafbfc}
.mismatch-row            .key-cell{background:#fffde7}
.mismatch-row:hover      .key-cell{background:#fff9c4}
.has-pending             .key-cell{background:#e3f2fd}
.has-pending:hover       .key-cell{background:#bbdefb}
.logical-diff-row        .key-cell{background:#f3e5f5}
.logical-diff-row:hover  .key-cell{background:#e1bee7}
.revert-all-btn{display:block;margin-top:4px;font-size:10px;background:none;
                border:1px solid #1565c0;color:#1565c0;border-radius:3px;
                padding:1px 5px;cursor:pointer}
.revert-all-btn:hover{background:#e3f2fd}

/* ── VALUE CELLS ── */
.val-cell{padding:6px 10px;border-right:1px solid #eef0f4;font-size:12px}
.val-cell:last-child{border-right:none}
.val-display{font-family:monospace;word-break:break-all;white-space:pre-wrap;
             max-width:var(--val-wrap,80ch);margin-bottom:3px}

/* ── COLUMN WIDTH / WRAP CONTROLS ── */
.col-width-ctrl{display:flex;align-items:center;gap:4px;font-size:11px;color:#555;
                border-left:1px solid #dde3ed;padding-left:10px;margin-left:4px}
.col-adj-btn{background:#f0f2f6;border:1px solid #c8d0dc;border-radius:3px;
             width:20px;height:20px;line-height:18px;text-align:center;
             cursor:pointer;font-size:13px;padding:0;color:#333;flex-shrink:0}
.col-adj-btn:hover{background:#dde3ed}
.col-width-disp{min-width:32px;text-align:center;font-weight:600;color:#1e2a3a;font-size:11px}
.wrap-inp{width:44px;font-size:11px;padding:1px 4px;border:1px solid #c8d0dc;
          border-radius:3px;text-align:center}
.col-ctrl-sep{color:#bbb;margin:0 4px}
.cell-mismatch .val-display{color:#b71c1c;font-weight:600}
.cell-pending .val-display .orig-struck{text-decoration:line-through;color:#999;margin-right:4px}
.cell-pending .val-display .new-val{color:#1565c0;font-weight:600;
                                    background:#e3f2fd;padding:1px 4px;border-radius:3px}
.cell-actions{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.use-btn{background:#1565c0;color:#fff;border:none;border-radius:3px;
         padding:2px 7px;font-size:11px;cursor:pointer}
.use-btn:hover{background:#0d47a1}
.override-btn{background:#fff;border:1px solid #aaa;border-radius:3px;
              padding:2px 6px;font-size:11px;cursor:pointer;color:#444}
.override-btn:hover{background:#f5f5f5}
.revert-btn{background:#fff;border:1px solid #ef9a9a;color:#c62828;border-radius:3px;
            padding:2px 6px;font-size:11px;cursor:pointer}
.revert-btn:hover{background:#ffebee}
.override-wrap{margin-top:5px;display:none;background:#f9fbe7;border:1px solid #c5e1a5;
               border-radius:4px;padding:5px;gap:4px;flex-direction:column}
.override-wrap.open{display:flex}
.override-input{padding:4px 7px;border:1px solid #aaa;border-radius:3px;font-size:12px;
                font-family:monospace;width:100%}
.override-actions{display:flex;gap:4px;align-items:center}
.apply-btn{background:#388e3c;color:#fff;border:none;border-radius:3px;
           padding:2px 8px;font-size:11px;cursor:pointer}
.cancel-btn{background:#fff;border:1px solid #aaa;border-radius:3px;
            padding:2px 6px;font-size:11px;cursor:pointer}
.override-hint{font-size:10px;color:#888;margin-left:4px}

/* ── MISSING / ABSENT CELLS ── */
.key-missing-cell{padding:6px 10px;background:repeating-linear-gradient(
  45deg,#fff,#fff 4px,#fff8e1 4px,#fff8e1 8px);border-right:1px solid #eef0f4}
.missing-lbl{color:#e65100;font-size:11px;font-style:italic}
.add-btn{background:#fff;border:1px solid #43a047;color:#2e7d32;border-radius:3px;
         padding:2px 7px;font-size:11px;cursor:pointer;margin-top:3px;display:inline-block}
.add-btn:hover{background:#e8f5e9}
.file-absent-cell{padding:6px 10px;background:repeating-linear-gradient(
  45deg,#f5f5f5,#f5f5f5 4px,#eeeeee 4px,#eeeeee 8px);border-right:1px solid #eef0f4}
.absent-lbl{color:#9e9e9e;font-size:11px;font-style:italic}

/* ── BINARY TABLE (full width) ── */
.binary-table{width:100%;border-collapse:collapse;margin:0}
.binary-table th{background:#37474f;color:#fff;padding:8px 14px;font-size:12px;text-align:left}
.binary-table td{padding:8px 14px;font-size:12px;border-bottom:1px solid #eee}
.binary-table .mismatch-row td{background:#fffde7}
.node-name-cell{font-weight:600;color:#1e2a3a}
.mono{font-family:monospace;font-size:11px;word-break:break-all}
.absent-cell{color:#9e9e9e;font-style:italic}

/* ── TEXT / XML COMPARE (full width) ── */
.raw-hdr{padding:10px 20px 6px;font-size:12px;font-weight:600;color:#555;
         border-top:1px solid #eef0f4;margin-top:10px}
.raw-table{width:100%;border-collapse:collapse;margin-top:0;table-layout:fixed}
.raw-table thead{position:sticky;top:0;z-index:10}
.raw-table th{background:#f0f2f6;padding:6px 14px;font-size:12px;font-weight:600;
              color:#444;border-bottom:1px solid #dde3ed;border-right:1px solid #dde3ed}
.raw-table th:last-child{border-right:none}
.raw-col{padding:0;vertical-align:top;border-right:1px solid #dde3ed;width:50%}
.raw-col:last-child{border-right:none}
.raw-content{padding:10px 14px;font-size:11px;font-family:monospace;
             white-space:pre-wrap;word-break:break-all;
             background:#fafafa;margin:0;line-height:1.5;width:100%}

/* ── EXPECTED DIFF (auto-detected instance-specific) ── */
.expected-diff-row td{background:#e0f7fa}
.expected-diff-row:hover td{background:#b2ebf2}
.expected-diff-row .key-cell{background:#e0f7fa}
.expected-diff-row:hover .key-cell{background:#b2ebf2}
.expected-diff-lbl{color:#00838f;font-size:10px;font-style:italic;display:block;margin-top:2px}
.cell-expected-diff .val-display{color:#006064}
.expected-diff-badge{background:#00838f;color:#fff;font-size:10px;border-radius:8px;
                     padding:1px 6px;flex-shrink:0;margin-left:4px}

/* ── SKIPPED FILES PANEL ── */
.skipped-panel{margin:20px;border:1px solid #dde3ed;border-radius:4px;background:#fff}
.skipped-panel-hdr{display:flex;align-items:center;gap:8px;padding:10px 16px;
                   background:#f8fafc;border-bottom:1px solid #dde3ed;cursor:pointer;
                   font-size:12px;font-weight:700;color:#555;user-select:none}
.skipped-panel-hdr:hover{background:#eef2f8}
.skipped-panel-body{padding:0}
.skipped-subsection{border-top:1px solid #eef0f4}
.skipped-subsec-hdr{padding:7px 16px;font-size:11px;font-weight:700;color:#777;
                    background:#fafafa;text-transform:uppercase;letter-spacing:.4px}
.skipped-table{width:100%;border-collapse:collapse}
.skipped-table th{background:#f0f2f6;padding:6px 12px;font-size:11px;font-weight:600;
                  color:#444;text-align:left;border-bottom:1px solid #dde3ed}
.skipped-table td{padding:5px 12px;font-size:11px;border-bottom:1px solid #f0f2f6;
                  font-family:monospace;color:#555}
.skipped-table tr:hover td{background:#fafbfc}
.skipped-copy-btn{background:#fff;border:1px solid #aaa;border-radius:3px;
                  padding:1px 6px;font-size:10px;cursor:pointer;color:#555;margin-left:4px}
.skipped-copy-btn:hover{background:#f5f5f5}

/* ── REPORT ERRORS PANEL ── */
.errors-panel{margin:20px;border:1px solid #ffcdd2;border-radius:4px;background:#fff}
.errors-panel-hdr{display:flex;align-items:center;gap:8px;padding:10px 16px;
                  background:#ffebee;border-bottom:1px solid #ffcdd2;cursor:pointer;
                  font-size:12px;font-weight:700;color:#c62828;user-select:none}
.errors-panel-hdr:hover{background:#ffcdd2}
.errors-table{width:100%;border-collapse:collapse}
.errors-table th{background:#ffebee;padding:6px 12px;font-size:11px;font-weight:600;
                 color:#c62828;text-align:left;border-bottom:1px solid #ffcdd2}
.errors-table td{padding:5px 12px;font-size:11px;border-bottom:1px solid #ffeaea;
                 vertical-align:top}
.errors-table td.mono{font-family:monospace;color:#b71c1c}

/* ── EMPTY STATE ── */
.empty-panel{padding:60px 30px;text-align:center;color:#999}

/* ── CHANGE LOG MODAL ── */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:500}
.modal-overlay.open{display:flex;align-items:center;justify-content:center}
.modal{background:#fff;border-radius:6px;box-shadow:0 8px 32px rgba(0,0,0,.3);
       width:min(900px,95vw);max-height:80vh;display:flex;flex-direction:column;overflow:hidden}
.modal-hdr{background:#1e2a3a;color:#fff;padding:12px 18px;display:flex;
           align-items:center;gap:10px}
.modal-hdr h2{flex:1;font-size:14px;font-weight:600}
.modal-close{background:none;border:none;color:#9ab;font-size:18px;cursor:pointer;padding:0 4px}
.modal-close:hover{color:#fff}
.modal-toolbar{padding:8px 18px;border-bottom:1px solid #eee;display:flex;gap:8px;
               align-items:center;flex-wrap:wrap}
.modal-body{overflow-y:auto;padding:0}
.cl-table{width:100%;border-collapse:collapse}
.cl-table th{background:#f0f2f6;padding:7px 12px;font-size:11px;font-weight:700;
             color:#444;border-bottom:2px solid #dde3ed;text-align:left;position:sticky;top:0}
.cl-table td{padding:6px 12px;font-size:12px;border-bottom:1px solid #eef0f4;
             vertical-align:top}
.cl-table tr:hover td{background:#fafafa}
.cl-file{font-family:monospace;font-size:11px;color:#555}
.cl-key{font-family:monospace;font-size:12px;color:#1e2a3a;font-weight:600}
.cl-orig{font-family:monospace;font-size:11px;color:#888;text-decoration:line-through}
.cl-new{font-family:monospace;font-size:11px;color:#1565c0;font-weight:600}
.cl-action{font-size:10px;border-radius:3px;padding:1px 7px;font-weight:700}
.cl-modified{background:#e3f2fd;color:#1565c0}
.cl-added{background:#e8f5e9;color:#2e7d32}
.cl-empty{padding:40px;text-align:center;color:#999;font-size:13px}
.cl-node{font-size:11px;color:#555}
.modal-footer{padding:8px 18px;border-top:1px solid #eee;display:flex;
              justify-content:flex-end;gap:8px}
.btn-primary{background:#1565c0;color:#fff;border:none;border-radius:4px;
             padding:6px 14px;font-size:12px;cursor:pointer}
.btn-primary:hover{background:#0d47a1}
.btn-secondary{background:#fff;border:1px solid #aaa;border-radius:4px;
               padding:6px 14px;font-size:12px;cursor:pointer;color:#444}
.btn-secondary:hover{background:#f5f5f5}
.modal-sm{width:min(480px,95vw);max-height:none}
.modal-sm .modal-body{padding:18px 20px;font-size:13px;color:#333;line-height:1.5}
.modal-sm .modal-body p{margin-bottom:10px}
.modal-sm .modal-body input{width:100%;padding:6px 10px;border:1px solid #c0c8d8;
                             border-radius:4px;font-size:13px;margin-top:6px}
.btn-default{background:#1565c0;color:#fff;border:none;border-radius:4px;
             padding:6px 14px;font-size:12px;cursor:pointer;font-weight:600}
.btn-default:hover{background:#0d47a1}

/* ── LEGEND ── */
.legend-bar{position:fixed;bottom:0;left:0;right:0;background:#fff;
            border-top:1px solid #dde3ed;padding:5px 22px;display:flex;
            gap:18px;align-items:center;font-size:11px;color:#555;z-index:300;
            flex-wrap:wrap}
.legend-bar .lbl{color:#999;font-size:10px;font-weight:700;margin-right:6px}
.leg-item{display:flex;align-items:center;gap:5px}
.leg-swatch{width:14px;height:14px;border-radius:3px;flex-shrink:0}

/* ── SKIP BUTTON (Phase 4.2) ── */
.skip-btn{background:#607d8b;color:#fff;border:none;border-radius:3px;
          padding:2px 7px;font-size:11px;cursor:pointer;margin-left:4px}
.skip-btn:hover{background:#455a64}
.unskip-btn{background:#90a4ae;color:#fff;border:none;border-radius:3px;
             padding:2px 7px;font-size:11px;cursor:pointer;margin-left:4px}
.unskip-btn:hover{background:#607d8b}
.skipped-row td{background:#f5f5f5 !important;opacity:.65}
.skipped-row .key-cell{background:#f5f5f5 !important}
.skipped-lbl{font-size:10px;font-style:italic;color:#888;display:block;margin-top:1px}

/* ── MISMATCH NAVIGATION (Phase 4.3) ── */
.mm-nav{display:flex;align-items:center;gap:6px;margin-left:8px}
.mm-nav-btn{background:#1e2a3a;color:#cde;border:1px solid #3d5068;border-radius:4px;
            padding:3px 10px;font-size:11px;cursor:pointer}
.mm-nav-btn:hover{background:#2e3d52}
.mm-nav-counter{font-size:11px;color:#555;min-width:80px;text-align:center}
.mm-nav-pulse{animation:mm-pulse .8s ease-out}
@keyframes mm-pulse{0%{background:#fffde7}50%{background:#ffe082}100%{}}

/* ── RESIZABLE COLUMNS (Phase 4.4) ── */
.audit-table th{position:relative}
.audit-table th::after{content:'';position:absolute;right:0;top:0;bottom:0;
                        width:5px;cursor:col-resize;background:transparent}
.audit-table th:hover::after{background:rgba(255,255,255,.2)}
"""


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS = r"""
'use strict';

const NODES      = AUDIT_DATA.nodes;
const NODE_DIRS  = AUDIT_DATA.nodeDirs;
const OUTPUT_DIR = AUDIT_DATA.outputDir || '';
const FILES      = AUDIT_DATA.files;
const RUN_AT     = AUDIT_DATA.runAt;
const SKIPPED_BACKUPS = AUDIT_DATA.skippedBackups || [];
const FILTERED_FILES  = AUDIT_DATA.filteredFiles  || [];
const RENDER_ERRORS   = AUDIT_DATA.renderErrors   || [];

let currentFileIdx  = -1;
let showDiffsOnly   = false;
let sidebarDiffsOnly = false;

// Column width & wrap state (U-16)
let _colWidth = null;   // px, null = use _nodeColWidth() default
let _valWrap  = 80;     // chars; 0 = no wrap

// pending[fileIdx][compound][node] = newValue (string)
const pending = {};

// changeLog: array of {ts, action, fileIdx, file, compound, key, node, orig, corrected}
const changeLog = [];

// ── State persistence (localStorage) ─────────────────────────────────
const _STATE_KEY = 'cm_state_v2_' + (RUN_AT || '');
let _localOutputDir = '';    // user-set when OUTPUT_DIR not configured
let _savedFileIdxSet = new Set();
let _pendingNavTo    = -1;   // target fileIdx during nav-guard prompt

function _effectiveOutputDir() {
  return (OUTPUT_DIR || _localOutputDir || '').trim();
}

function _saveState() {
  try {
    localStorage.setItem(_STATE_KEY, JSON.stringify({
      p: pending, s: skipped, c: changeLog, d: _localOutputDir,
    }));
  } catch(e) {}
}

function _restoreState() {
  try {
    let raw = localStorage.getItem(_STATE_KEY);
    if (!raw) return;
    let st = JSON.parse(raw);
    if (st.p) Object.keys(st.p).forEach(fi => {
      let n = parseInt(fi, 10); if (!isNaN(n)) pending[n] = st.p[fi];
    });
    if (st.s) Object.keys(st.s).forEach(fi => {
      let n = parseInt(fi, 10); if (!isNaN(n)) skipped[n] = st.s[fi];
    });
    if (st.c && Array.isArray(st.c)) st.c.forEach(e => {
      e.fileIdx = parseInt(e.fileIdx, 10);
      changeLog.push(e);
    });
    if (st.d) _localOutputDir = st.d;
  } catch(e) {}
}

// ── Save helpers ──────────────────────────────────────────────────────

function _saveFileChanges(fi) {
  let effDir = _effectiveOutputDir();
  if (!effDir) return false;
  let file = FILES[fi];
  if (!file || file.type === 'binary') return false;
  let saved = false;
  NODES.forEach(n => {
    if (!_anyPendingForFileNode(fi, n)) return;
    let content = reconstructContent(fi, file, n);
    if (content === null) return;
    let fname = file.path.split('/').pop();
    _blobDownload(content, fname, 'text/plain');
    saved = true;
  });
  if (saved) _savedFileIdxSet.add(fi);
  return saved;
}

function _hasUnsavedChanges(fi) {
  return _anyPendingForFile(fi) && !_savedFileIdxSet.has(fi);
}

function _showSaveStatus(msg) {
  let el = document.getElementById('save-status-msg');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'inline-block';
  setTimeout(() => { el.style.display = 'none'; }, 4000);
}

// ── Save All Changes ──────────────────────────────────────────────────

function saveAllChanges() {
  let effDir = _effectiveOutputDir();
  if (!effDir) { _showOutputDirPrompt('all'); return; }
  _doSaveAll(effDir);
}

function _doSaveAll(effDir) {
  let count = 0;
  FILES.forEach((file, fi) => {
    if (file.type === 'binary') return;
    NODES.forEach(n => {
      if (!_anyPendingForFileNode(fi, n)) return;
      let content = reconstructContent(fi, file, n);
      if (content === null) return;
      _blobDownload(content, file.path.split('/').pop(), 'text/plain');
      _savedFileIdxSet.add(fi);
      count++;
    });
  });
  if (!count) { alert('No changes to save.'); return; }
  _showSaveStatus('\u2713 Saved ' + count + ' file(s) \u2192 ' + effDir + '/[Node]/[path]');
}

// ── Output-dir prompt modal ───────────────────────────────────────────
let _outputDirAction = '';  // 'all' | 'file'
let _outputDirFileFi = -1;

function _showOutputDirPrompt(action, fi) {
  _outputDirAction = action || 'all';
  _outputDirFileFi = (fi !== undefined) ? fi : -1;
  let inp = document.getElementById('od-input');
  if (inp) { inp.value = 'corrections'; setTimeout(() => inp.focus(), 50); }
  let el = document.getElementById('od-modal');
  if (el) el.classList.add('open');
}

function outputDirConfirm() {
  let inp = document.getElementById('od-input');
  let dir = (inp ? inp.value : '').trim();
  if (!dir) return;
  _localOutputDir = dir;
  _saveState();
  let el = document.getElementById('od-modal');
  if (el) el.classList.remove('open');
  if (_outputDirAction === 'all') {
    _doSaveAll(dir);
  } else if (_outputDirAction === 'file' && _outputDirFileFi >= 0) {
    _saveFileChanges(_outputDirFileFi);
    if (_pendingNavTo >= 0) { let t = _pendingNavTo; _pendingNavTo = -1; _doSelectFile(t); }
  }
}

function outputDirCancel() {
  let el = document.getElementById('od-modal');
  if (el) el.classList.remove('open');
  _pendingNavTo = -1;
}

// ── Navigation guard modal ────────────────────────────────────────────

function _showNavGuard(fi) {
  let file = FILES[fi];
  let fname = file ? file.path : 'this file';
  let el = document.getElementById('navguard-modal');
  let msg = document.getElementById('navguard-msg');
  if (msg) msg.textContent = '\u26A0 Unsaved changes in: ' + fname;
  let sub = document.getElementById('navguard-sub');
  let effDir = _effectiveOutputDir();
  if (sub) sub.textContent = effDir
    ? 'Files will be saved to: ' + effDir + '/' + (file ? FILES[fi].path.split('/').pop() : '')
    : 'No output directory configured.';
  if (el) {
    el.classList.add('open');
    // Default focus = Save & Continue button
    let btn = document.getElementById('navguard-save-btn');
    if (btn) setTimeout(() => btn.focus(), 50);
  }
}

function navGuardSaveAndContinue() {
  let el = document.getElementById('navguard-modal');
  if (el) el.classList.remove('open');
  let fi = currentFileIdx;
  let effDir = _effectiveOutputDir();
  if (!effDir) {
    _showOutputDirPrompt('file', fi);
    return;
  }
  _saveFileChanges(fi);
  if (_pendingNavTo >= 0) { let t = _pendingNavTo; _pendingNavTo = -1; _doSelectFile(t); }
}

function navGuardContinue() {
  let el = document.getElementById('navguard-modal');
  if (el) el.classList.remove('open');
  if (_pendingNavTo >= 0) { let t = _pendingNavTo; _pendingNavTo = -1; _doSelectFile(t); }
}

function navGuardCancel() {
  let el = document.getElementById('navguard-modal');
  if (el) el.classList.remove('open');
  _pendingNavTo = -1;
}

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // Restore state from localStorage (persists across page refreshes)
  _restoreState();

  renderDiffQuickList();
  renderSidebar();
  _buildMismatchIndex();
  renderSkippedPanel();
  renderErrorsPanel();

  // Init tab counts so user can see at a glance what's in each tab
  let skCount  = SKIPPED_BACKUPS.length;
  let flCount  = FILTERED_FILES.length;
  let skBadge  = document.getElementById('tab-count-skipped');
  let flBadge  = document.getElementById('tab-count-filtered');
  if (skBadge) { skBadge.textContent = skCount; if (skCount) skBadge.classList.add('has-items'); }
  if (flBadge) { flBadge.textContent = flCount; if (flCount) flBadge.classList.add('has-items'); }

  // Auto-enable sidebar diffs-only when diffs/absent are a small minority of files
  let diffCount = FILES.filter(f => f.mismatchCount > 0 || (f.absentCount||0) > 0).length;
  if (diffCount > 0 && diffCount < FILES.length * 0.5) {
    sidebarDiffsOnly = true;
    let btn = document.getElementById('sidebar-diffs-toggle');
    if (btn) btn.classList.add('active');
    // _applyDiffsOnlyFilter() will be called after renderSidebar already ran;
    // apply it again now that the flag is set
    _applyDiffsOnlyFilter();
  }

  let idx = FILES.findIndex(f => f.mismatchCount > 0 || (f.absentCount||0) > 0);
  if (idx < 0) idx = 0;

  // Handle deep-link from index page: hash = URL-encoded file path
  let hash = window.location.hash;
  if (hash) {
    try {
      let targetPath = decodeURIComponent(hash.slice(1));
      let hashIdx = FILES.findIndex(f => f.path === targetPath);
      if (hashIdx >= 0) idx = hashIdx;
    } catch(e) {}
  }

  // U-16: init col width and val-wrap from localStorage
  let savedCW = localStorage.getItem('cm_col_width');
  _colWidth = savedCW ? parseInt(savedCW, 10) : _nodeColWidth();
  let savedWrap = localStorage.getItem('cm_val_wrap');
  _valWrap = savedWrap !== null ? parseInt(savedWrap, 10) : 80;
  _applyWrapCss(_valWrap);

  // Refresh change counter to reflect restored state
  updateChangeCounter();

  if (FILES.length > 0) _doSelectFile(idx);
});

// ── Diff quick-list (files with diffs or absent nodes) ────────────────
function renderDiffQuickList() {
  let ql = document.getElementById('diff-quicklist');
  if (!ql) return;
  let diffFiles = FILES.map((f, i) => ({f, i}))
    .filter(({f}) => f.mismatchCount > 0 || (f.absentCount||0) > 0);
  if (!diffFiles.length) { ql.style.display = 'none'; return; }

  let items = diffFiles.map(({f, i}) => {
    let badges = '';
    if (f.mismatchCount > 0)
      badges += `<span class="diff-qbadge">${f.mismatchCount}</span>`;
    if ((f.absentCount||0) > 0)
      badges += `<span class="diff-qbadge" style="background:#e65100">&#9888;</span>`;
    return `<div class="diff-qfile" onclick="selectFile(${i})">
       <span class="diff-qname">${esc(f.path.split('/').pop())}</span>
       ${badges}
     </div>`;
  }).join('');

  let hdr = ql.querySelector('.diff-quicklist-hdr');
  if (hdr) hdr.innerHTML =
    `<span class="dir-chev">&#9660;</span>
     <span style="flex:1">&#9888; ${diffFiles.length} file${diffFiles.length!==1?'s':''} with differences or absent nodes</span>`;

  let body = ql.querySelector('.diff-quicklist-body');
  if (body) body.innerHTML = items;
}

function toggleDiffQuickList(hdr) {
  let body = hdr.nextElementSibling;
  let chev = hdr.querySelector('.dir-chev');
  let open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (chev) chev.innerHTML = open ? '&#9654;' : '&#9660;';
}

// ── Tree sidebar ──────────────────────────────────────────────────────
// Builds a recursive tree: {name, path, dirs:{}, files:[], diffCount, missingCount, totalCount}
function _buildTree() {
  let root = {name:'', path:'', dirs:{}, files:[], diffCount:0, missingCount:0, totalCount:0};
  FILES.forEach((f, idx) => {
    let segs = f.path.split('/');
    let node = root;
    for (let i = 0; i < segs.length - 1; i++) {
      let seg = segs[i];
      if (!node.dirs[seg]) {
        node.dirs[seg] = {name:seg, path:segs.slice(0,i+1).join('/'),
                          dirs:{}, files:[], diffCount:0, missingCount:0, totalCount:0};
      }
      node = node.dirs[seg];
    }
    let fname    = segs[segs.length-1];
    let absentCnt = f.absentCount || 0;
    let isAbsent  = absentCnt > 0;
    let hasDiff   = f.mismatchCount > 0;
    node.files.push({idx, name:fname, f, hasDiff, isAbsent});
    node.totalCount++;
    if (hasDiff)   node.diffCount++;
    if (isAbsent)  node.missingCount++;  // count all absent (incl. diff+absent)
  });
  // Bubble counts up
  function bubble(n) {
    Object.values(n.dirs).forEach(sub => {
      bubble(sub);
      n.diffCount    += sub.diffCount;
      n.missingCount += sub.missingCount;
      n.totalCount   += sub.totalCount;
    });
  }
  bubble(root);
  return root;
}

function renderSidebar() {
  let sb = document.getElementById('sidebar-tree');
  if (!sb) return;
  let tree = _buildTree();
  let html = '';
  // Root-level files (no subdirectory)
  if (tree.files.length) html += _renderDirBody(tree, 0);
  // Subdirectories
  html += Object.values(tree.dirs).map(d => _renderDirNode(d, 0)).join('');
  sb.innerHTML = html || '<div style="padding:12px;font-size:11px;color:#999">No files.</div>';
  _applyDiffsOnlyFilter();
}

function _renderDirNode(dir, depth) {
  let indent = depth * 12;
  let hasDiffs = dir.diffCount > 0;
  let hasMiss  = dir.missingCount > 0;
  let badge = (hasDiffs && hasMiss)
    ? `<span class="dir-diff-badge">${dir.diffCount} diff${dir.diffCount!==1?'s':''}</span><span class="dir-missing-badge">&#9888;</span>`
    : hasDiffs
      ? `<span class="dir-diff-badge">${dir.diffCount} diff${dir.diffCount!==1?'s':''}</span>`
      : hasMiss
        ? `<span class="dir-missing-badge">&#9888;</span>`
        : `<span class="dir-ok-badge">&#10003;</span>`;
  // Auto-collapse dirs where everything matches
  let autoOpen = hasDiffs || hasMiss;
  let chevron  = autoOpen ? '&#9660;' : '&#9654;';
  let bodyDisplay = autoOpen ? '' : 'none';
  let children = Object.values(dir.dirs).map(d => _renderDirNode(d, depth+1)).join('');
  let files    = _renderDirBody(dir, depth+1);

  return `<div class="tree-dir" data-diff="${hasDiffs?1:0}" data-path="${esa(dir.path)}">
    <div class="tree-dir-hdr" style="padding-left:${8+indent}px" onclick="toggleDir(this)">
      <span class="dir-chev">${chevron}</span>
      <span class="tree-dir-name" title="${esc(dir.path)}">${esc(dir.name)}/</span>
      ${badge}
    </div>
    <div class="tree-dir-body" style="display:${bodyDisplay}">${children}${files}</div>
  </div>`;
}

function _renderDirBody(dir, depth) {
  let indent = depth * 12;
  return dir.files.map(({idx, name, f, hasDiff, isAbsent}) => {
    let badge = _sidebarBadge(idx, f);
    let diffAttr = (hasDiff || isAbsent) ? '1' : '0';  // absent files also shown in diffs-only mode
    return `<div class="tree-file" data-idx="${idx}" data-diff="${diffAttr}"
              style="padding-left:${8+indent}px"
              onclick="selectFile(${idx})">
      <span class="tree-file-name" title="${esc(f.path)}">${esc(name)}</span>${badge}
    </div>`;
  }).join('');
}

function _sidebarBadge(fileIdx, f) {
  let hasPend    = _anyPendingForFile(fileIdx);
  let absentCnt  = f.absentCount || 0;
  let parts      = [];
  if (hasPend)
    parts.push(`<span class="pending-badge">&#9998;</span>`);
  // Show mismatch badge and absent badge independently so both are visible
  if (f.mismatchCount > 0)
    parts.push(`<span class="mismatch-badge">${f.mismatchCount}</span>`);
  if (absentCnt > 0)
    parts.push(`<span class="missing-file-badge">&#9888; ${absentCnt}&nbsp;absent</span>`);
  if ((f.logicalDiffCount||0) > 0)
    parts.push(`<span class="logical-badge">~${f.logicalDiffCount}</span>`);
  if (!parts.length) {
    if (f.contentSkipped) {
      // Large identical file — show size of first node instead of plain ✓
      let sizes = f.fileSizes || {};
      let firstSz = Object.values(sizes)[0] || 0;
      let szLabel = firstSz >= 1048576
        ? (firstSz / 1048576).toFixed(1) + ' MB'
        : firstSz >= 1024
          ? Math.round(firstSz / 1024) + ' KB'
          : firstSz + ' B';
      parts.push(`<span class="ok-badge" title="Identical — diff skipped">&#9989; ${szLabel}</span>`);
    } else {
      parts.push(`<span class="ok-badge">&#10003;</span>`);
    }
  }
  return parts.join('');
}

// BUG-06: refresh sidebar badge for a specific file after state change
function refreshSidebarBadge(fileIdx) {
  let f   = FILES[fileIdx];
  let el  = document.querySelector(`.tree-file[data-idx="${fileIdx}"]`);
  if (!el) return;
  // Replace all badge spans
  let badgeSpans = el.querySelectorAll('.mismatch-badge,.ok-badge,.pending-badge,.missing-file-badge,.logical-badge');
  badgeSpans.forEach(s => s.remove());
  let newBadge = _sidebarBadge(fileIdx, f);
  let tmp = document.createElement('span');
  tmp.innerHTML = newBadge;
  while (tmp.firstElementChild) el.appendChild(tmp.firstElementChild);
  // Also update parent dir badges
  _refreshDirBadges();
}

function _refreshDirBadges() {
  document.querySelectorAll('.tree-dir').forEach(dirEl => {
    let fileEls = dirEl.querySelectorAll(':scope > .tree-dir-body > .tree-file');
    let diffCount = 0;
    fileEls.forEach(fe => { if (fe.dataset.diff === '1') diffCount++; });
    // Also count nested diff dirs
    let nestedDiffs = dirEl.querySelectorAll('.tree-file[data-diff="1"]').length;
    let hasPend = dirEl.querySelectorAll('.pending-badge').length > 0;
    let hdr = dirEl.querySelector(':scope > .tree-dir-hdr');
    if (!hdr) return;
    let badge = hdr.querySelector('.dir-diff-badge,.dir-ok-badge,.dir-missing-badge');
    if (!badge) return;
    if (nestedDiffs > 0 || hasPend) {
      badge.className = 'dir-diff-badge';
      badge.textContent = `${nestedDiffs} diff${nestedDiffs!==1?'s':''}`;
    } else {
      badge.className = 'dir-ok-badge';
      badge.textContent = '✓';
    }
  });
}

function toggleDir(hdr) {
  let body = hdr.nextElementSibling;
  let chev = hdr.querySelector('.dir-chev');
  let open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  chev.innerHTML = open ? '&#9654;' : '&#9660;';
}

// Diffs-only sidebar filter
function toggleSidebarDiffsOnly() {
  sidebarDiffsOnly = !sidebarDiffsOnly;
  let btn = document.getElementById('sidebar-diffs-toggle');
  if (btn) btn.classList.toggle('active', sidebarDiffsOnly);
  _applyDiffsOnlyFilter();
}

function _applyDiffsOnlyFilter() {
  document.querySelectorAll('.tree-file').forEach(el => {
    let hasDiff = el.dataset.diff === '1';
    el.style.display = (sidebarDiffsOnly && !hasDiff) ? 'none' : '';
  });
  // Hide dirs where all children are hidden; also collapse fully-matched dirs in diffsOnly mode
  document.querySelectorAll('.tree-dir').forEach(dirEl => {
    let anyVis = Array.from(dirEl.querySelectorAll('.tree-file'))
                      .some(f => f.style.display !== 'none');
    dirEl.style.display = anyVis ? '' : 'none';
    if (sidebarDiffsOnly && dirEl.dataset.diff === '0') {
      let body = dirEl.querySelector('.tree-dir-body');
      let chev = dirEl.querySelector('.dir-chev');
      if (body) body.style.display = 'none';
      if (chev) chev.innerHTML = '&#9654;';
    }
  });
}

// Search filter — works with tree
function filterFiles(val) {
  let q = val.toLowerCase();
  if (!q) {
    _applyDiffsOnlyFilter();
    _updateSearchBadge(0, true);
    return;
  }
  let matchCount = 0;
  document.querySelectorAll('.tree-file').forEach(el => {
    let name = (el.querySelector('.tree-file-name') || el).textContent.toLowerCase();
    let vis  = name.includes(q);
    el.style.display = vis ? '' : 'none';
    if (vis) matchCount++;
  });
  document.querySelectorAll('.tree-dir').forEach(dirEl => {
    let anyVis = Array.from(dirEl.querySelectorAll('.tree-file'))
                      .some(f => f.style.display !== 'none');
    dirEl.style.display = anyVis ? '' : 'none';
    if (anyVis) {
      let body = dirEl.querySelector('.tree-dir-body');
      let chev = dirEl.querySelector('.dir-chev');
      if (body) body.style.display = '';
      if (chev) chev.innerHTML = '&#9660;';
    }
  });
  _updateSearchBadge(matchCount, false);
}

function _updateSearchBadge(count, hidden) {
  let badge = document.getElementById('search-match-badge');
  if (!badge) return;
  if (hidden || count === 0) {
    badge.textContent = hidden ? '' : 'No matches';
    badge.style.display = hidden ? 'none' : 'inline';
    badge.style.background = hidden ? '' : '#c62828';
  } else {
    badge.textContent = count + ' match' + (count !== 1 ? 'es' : '');
    badge.style.display = 'inline';
    badge.style.background = '#2e7d32';
  }
}

function _searchFirstVisible() {
  let el = document.querySelector('.tree-file[style=""],.tree-file:not([style])');
  // Find first visible tree-file
  let all = document.querySelectorAll('.tree-file');
  for (let i = 0; i < all.length; i++) {
    if (all[i].style.display !== 'none') {
      let idx = parseInt(all[i].getAttribute('data-idx'), 10);
      if (!isNaN(idx)) selectFile(idx);
      return;
    }
  }
}

function clearFileSearch() {
  let inp = document.getElementById('sidebar-search-input');
  if (inp) { inp.value = ''; filterFiles(''); inp.focus(); }
}

// Global keyboard shortcut: Ctrl+K focuses the sidebar search
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    let inp = document.getElementById('sidebar-search-input');
    if (inp) { inp.focus(); inp.select(); }
  }
});

// ── File selection ─────────────────────────────────────────────────────
function selectFile(idx) {
  // Nav guard: if current file has unsaved changes, prompt before leaving
  if (currentFileIdx >= 0 && currentFileIdx !== idx && _hasUnsavedChanges(currentFileIdx)) {
    _pendingNavTo = idx;
    _showNavGuard(currentFileIdx);
    return;
  }
  _doSelectFile(idx);
}

function _doSelectFile(idx) {
  currentFileIdx = idx;

  document.querySelectorAll('.tree-file').forEach(el => el.classList.remove('active'));
  let item = document.querySelector(`.tree-file[data-idx="${idx}"]`);
  if (item) { item.classList.add('active'); item.scrollIntoView({block:'nearest'}); }

  renderFilePanel(idx);
  _buildMismatchIndex();

  // Re-sync diffs-only checkbox and apply filter (preserves user's toggle state)
  let chk = document.getElementById('diffs-only-chk');
  if (chk) chk.checked = showDiffsOnly;
  if (showDiffsOnly) applyDiffsFilter();
}

// ── Auto-detect expected diffs (instance-specific values) ────────────
// Detects params whose values differ only in a node-specific suffix/index.
// Pattern: all values share a common prefix/template, with a sequential number
// or node-specific label at a specific position.
const _LOG_KEY_RE = /log[._\-]?(?:file|prefix|dir|path|name)|(?:kpi|stats|snmp)[._\-].*prefix|logfile|logprefix|instance[._\-]?(?:name|number|id|num)|trap[._\-]file|interaction[._\-]prefix|input[._\-]file[._\-]prefix/i;

function _isExpectedDiff(param) {
  if (!param.hasMismatch) return false;
  // Rule 1: key name matches log/instance pattern
  if (_LOG_KEY_RE.test(param.key)) return true;
  // Rule 2: values differ only in a trailing sequential number or node-suffix
  // e.g. APP-01 vs APP-02, imas1.log vs imas2.log
  let vals = NODES.map(n => (param.values||{})[n]).filter(v => v !== null && v !== undefined);
  if (vals.length < 2) return false;
  // Try: all values same except last digit sequence — replace trailing digits → compare
  let normed = vals.map(v => String(v).replace(/\d+$/, '\x00').replace(/\d+(?=[^0-9]*$)/, '\x00'));
  if (new Set(normed).size === 1) return true;
  // Try: values are same except for a contiguous run of digits anywhere (APP-01 vs APP-02)
  let first = String(vals[0]);
  let allMatch = vals.every(v => {
    let s = String(v);
    if (s === first) return true;
    // Find position of first difference
    let i = 0;
    while (i < s.length && i < first.length && s[i] === first[i]) i++;
    // From that position, skip digits in both strings
    let j1 = i, j2 = i;
    while (j1 < first.length && /\d/.test(first[j1])) j1++;
    while (j2 < s.length   && /\d/.test(s[j2]))       j2++;
    // The rest should match
    return first.substring(j1) === s.substring(j2);
  });
  return allMatch;
}

// ── File panel ─────────────────────────────────────────────────────────
function renderFilePanel(idx) {
  let file  = FILES[idx];
  let panel = document.getElementById('main-panel');

  let presentList = file.presentIn.map(n => `<span class="node-tag">${esc(n)}</span>`).join(' ');
  let absentNodes = NODES.filter(n => !file.presentIn.includes(n));
  let absentList  = absentNodes.length
    ? `<span class="absent-tag">&#9888; Absent in: ${absentNodes.map(esc).join(', ')}</span>` : '';

  let dlBtns = '';
  if (file.type !== 'binary') {
    dlBtns = NODES
      .filter(n => file.presentIn.includes(n) || _anyPendingForFileNode(idx, n))
      .map(n => {
        let targetPath = OUTPUT_DIR
          ? OUTPUT_DIR.replace(/\/+$/,'') + '/' + n + '/' + file.path
          : '';
        let titleAttr = targetPath ? ` title="Save to: ${esc(targetPath)}"` : '';
        return `<button class="dl-btn" onclick="downloadConfig(${idx},'${esj(n)}','${esj(targetPath)}')"${titleAttr}>&#11015; ${esc(n)}</button>`;
      })
      .join('');
  }

  let warnHtml = '';
  if (file.warnings && file.warnings.length) {
    warnHtml = file.warnings.map(w =>
      `<div class="warn-banner">&#9888; ${esc(w)}</div>`
    ).join('');
  }

  // Content-skipped banner — large file, identical across all nodes
  let skipBannerHtml = '';
  if (file.contentSkipped) {
    let sizeChips = Object.entries(file.fileSizes || {}).map(([node, sz]) => {
      let label = sz >= 1048576
        ? (sz / 1048576).toFixed(2) + ' MB'
        : sz >= 1024
          ? (sz / 1024).toFixed(1) + ' KB'
          : sz + ' B';
      return `<span class="skip-size-chip">${esc(node)}: ${label}</span>`;
    }).join('');
    let paramNote = file.paramCount > 0
      ? `<br><span style="font-size:11px;color:#689f38">&#10004; ${file.paramCount} parameter(s) compared — all identical.</span>`
      : '';
    skipBannerHtml = `<div class="skip-banner">
      <div class="skip-banner-icon">&#9989;</div>
      <div class="skip-banner-body">
        <div class="skip-banner-title">Content identical across all nodes &mdash; diff display skipped</div>
        <div class="skip-banner-note">
          This file exceeds the 512 KB display threshold and is identical on all nodes.
          Raw diff is omitted to keep the report compact.${paramNote}
        </div>
        ${sizeChips ? `<div class="skip-banner-sizes">${sizeChips}</div>` : ''}
      </div>
    </div>`;
  }

  // Match/absent banner — shown when no content mismatches (non-skipped files)
  let matchHtml = '';
  let _absentCnt = file.absentCount || 0;
  if (!file.contentSkipped) {
    if (file.mismatchCount === 0 && (file.logicalDiffCount || 0) === 0 && file.type !== 'binary') {
      if (_absentCnt > 0) {
        // Content agrees among present nodes but file is missing from some
        matchHtml = `<div class="match-banner" style="border-left-color:#e65100;background:#fff8f0">
          <span class="match-icon" style="color:#e65100">&#9888;</span>
          <span>Content identical across <strong>${file.presentIn.length}</strong> present node(s), but file is <strong>absent from ${_absentCnt} node(s)</strong>.</span>
        </div>`;
      } else {
        matchHtml = `<div class="match-banner">
          <span class="match-icon">&#10003;</span>
          <span>All ${file.presentIn.length} nodes agree on every parameter in this file.</span>
        </div>`;
      }
    } else if (file.mismatchCount === 0 && (file.logicalDiffCount || 0) > 0) {
      let absentNote = _absentCnt > 0 ? ` File also absent from ${_absentCnt} node(s).` : '';
      matchHtml = `<div class="match-banner">
        <span class="match-icon">&#10003;</span>
        <span>No actionable mismatches. ${file.logicalDiffCount} parameter(s) differ as expected (node-specific values — shown in purple).${absentNote}</span>
      </div>`;
    }
  }

  let autoExpectedCount = (file.params||[]).filter(p => p.hasMismatch && _isExpectedDiff(p)).length;
  // When content was skipped, no table is needed
  let tableHtml = file.contentSkipped ? ''
    : file.type === 'binary'
      ? renderBinaryTable(file)
      : (file.type === 'xml' || file.type === 'text')
        ? renderTextCompare(file, idx)
        : file.type === 'error'
          ? renderErrorFile(file)
          : renderParamTable(file, idx);

  let expDiffMeta = autoExpectedCount > 0
    ? `&nbsp;&middot;&nbsp; <span style="color:#00838f">~${autoExpectedCount} instance-specific</span>` : '';
  let logDiffMeta = (file.logicalDiffCount||0) > 0
    ? `&nbsp;&middot;&nbsp; <span class="logical-tag">~${file.logicalDiffCount} expected</span>` : '';

  panel.innerHTML = `
    ${warnHtml}${skipBannerHtml}${matchHtml}
    <div class="panel-sticky-hdr">
      <div class="panel-file-hdr">
        <div class="panel-file-path">${esc(file.path)}</div>
        <div class="panel-file-meta">
          ${presentList}${absentList}
          ${file.mismatchCount > 0 ? `&nbsp;&middot;&nbsp; <strong>${file.mismatchCount}</strong> mismatch(es)` : ''}
          ${(file.absentCount||0) > 0 ? `&nbsp;&middot;&nbsp; <span style="color:#e65100;font-weight:bold">&#9888; absent from ${file.absentCount} node(s)</span>` : ''}
          ${file.mismatchCount === 0 && (file.absentCount||0) === 0 ? `&nbsp;&middot;&nbsp; <span style="color:#388e3c">&#10003; all matched</span>` : ''}
          ${expDiffMeta}${logDiffMeta}
          &nbsp;&middot;&nbsp; <em style="color:#888">${esc(file.type.toUpperCase())}</em>
          ${file.contentSkipped ? `&nbsp;&middot;&nbsp; <span style="color:#558b2f;font-size:11px">&#9989; diff skipped (large identical file)</span>` : ''}
        </div>
      </div>
      <div class="panel-toolbar">
        <label>
          <input type="checkbox" id="diffs-only-chk" onchange="toggleDiffsOnly(this.checked)">
          Show differences only
        </label>
        <label>
          <input type="checkbox" id="expected-diff-chk" checked onchange="toggleExpectedDiffsVisible(this.checked)">
          Show instance-specific
        </label>
        <label>
          <input type="checkbox" id="logical-only-chk" checked onchange="toggleLogicalVisible(this.checked)">
          Show expected diffs
        </label>
        <div class="col-width-ctrl">
          <span>Col&nbsp;width:</span>
          <button class="col-adj-btn" onclick="adjustColWidth(-20)" title="Narrower">&#8722;</button>
          <span class="col-width-disp" id="col-width-disp">—</span>
          <button class="col-adj-btn" onclick="adjustColWidth(+20)" title="Wider">&#43;</button>
          <span class="col-ctrl-sep">|</span>
          <span>Wrap:</span>
          <input class="wrap-inp" type="number" id="wrap-chars-inp" value="80" min="1" max="9999"
                 title="Wrap value text at N characters (leave blank or 0 for no wrap)"
                 onchange="applyWrap(+this.value)"
                 onkeydown="if(event.key==='Enter')applyWrap(+this.value)">
          <span>ch</span>
          <button class="col-adj-btn" onclick="clearWrap()" title="Remove wrap limit">&#8734;</button>
        </div>
        <div class="mm-nav">
          <button class="mm-nav-btn" onclick="prevMismatch()">&#9664; Prev</button>
          <span class="mm-nav-counter" id="mm-nav-counter">—</span>
          <button class="mm-nav-btn" onclick="nextMismatch()">Next &#9654;</button>
        </div>
        <div class="dl-group">${dlBtns}</div>
      </div>
    </div>
    <div class="table-wrap">${tableHtml}</div>`;
}

// ── Binary table ────────────────────────────────────────────────────────
function renderBinaryTable(file) {
  let presentMd5s = file.presentIn.map(n => (file.binary||{})[n] && file.binary[n].md5).filter(Boolean);
  let allSame     = new Set(presentMd5s).size === 1 && presentMd5s.length > 0;

  let rows = NODES.map(n => {
    let bi = file.binary ? file.binary[n] : null;
    if (!bi || !bi.present) {
      return `<tr><td class="node-name-cell">${esc(n)}</td>
        <td colspan="3" class="absent-cell">FILE ABSENT</td></tr>`;
    }
    let isMismatch = !allSame || !file.presentIn.includes(n);
    return `<tr class="${isMismatch ? 'mismatch-row' : ''}">
      <td class="node-name-cell" title="${esc(NODE_DIRS[n]||n)}">${esc(n)}</td>
      <td class="mono">${esc(bi.md5)}</td>
      <td>${fmtBytes(bi.size)}</td>
      <td>${!isMismatch ? '&#10003; Match' : '&#9888; Differs'}</td>
    </tr>`;
  }).join('');

  return `<table class="audit-table binary-table">
    <thead><tr>
      <th style="width:200px">Node</th><th>SHA-256 Checksum</th>
      <th>File Size</th><th>Status</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <p style="padding:0 20px;color:#888;font-size:11px;margin-top:8px">
    Binary file &mdash; parameter-level comparison not available.
    Compare checksums to verify identical content.
  </p>`;
}

function fmtBytes(b) {
  if (!b) return '0 B';
  if (b < 1024)    return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  return (b/1048576).toFixed(2) + ' MB';
}

// ── Text / XML compare ─────────────────────────────────────────────────
// BUG-08: use 'txt-' prefix for table id to avoid collision with kv 'ptbl-N'
function renderTextCompare(file, idx) {
  let md5Table = `<table class="audit-table param-table" id="txt-${idx}">` +
    `<thead><tr><th class="key-th">Parameter</th>` +
    NODES.map(n => {
      let absent = !file.presentIn.includes(n);
      return `<th class="val-th ${absent?'absent-node-hdr':''}" title="${esc(NODE_DIRS[n]||n)}">${esc(n)}</th>`;
    }).join('') +
    `</tr></thead><tbody>`;

  file.params.forEach((param, pi) => {
    md5Table += renderRow(file, idx, param, pi);
  });
  md5Table += `</tbody></table>`;

  let cols = file.presentIn.map(n => {
    let raw = (file.rawContent||{})[n] || '';
    return `<td class="raw-col"><pre class="raw-content">${esc(raw)}</pre></td>`;
  }).join('');
  let hdrs = file.presentIn.map(n => `<th>${esc(n)}</th>`).join('');

  return md5Table +
    `<p class="raw-hdr">File Content (side-by-side)</p>
     <table class="raw-table">
       <thead><tr>${hdrs}</tr></thead>
       <tbody><tr>${cols}</tr></tbody>
     </table>`;
}

// ── Node visibility (Phase 3.0) ──────────────────────────────────────
const hiddenNodes = new Set();

function _nodeColWidth() {
  const n = NODES.length;
  return n <= 4 ? 260 : n <= 8 ? 220 : n <= 16 ? 180 : 160;
}

function renderNodeSelector() {
  if (NODES.length <= 4) return '';
  let chips = NODES.map((n, i) =>
    `<button class="node-chip active" data-idx="${i}" onclick="toggleNode(${i})">${esc(n)}</button>`
  ).join('');
  return `<div class="node-selector">
    <span class="node-sel-label">Show nodes:</span>
    ${chips}
    <button class="node-sel-all" onclick="showAllNodes()">All</button>
    <button class="node-sel-none" onclick="hideAllNodes()">None</button>
  </div>`;
}

function toggleNode(nodeIdx) {
  hiddenNodes.has(nodeIdx) ? hiddenNodes.delete(nodeIdx) : hiddenNodes.add(nodeIdx);
  applyNodeVisibility();
}
function showAllNodes() { hiddenNodes.clear(); applyNodeVisibility(); }
function hideAllNodes() { NODES.forEach((_, i) => hiddenNodes.add(i)); applyNodeVisibility(); }

function applyNodeVisibility() {
  NODES.forEach((_, i) => {
    const hidden = hiddenNodes.has(i);
    document.querySelectorAll(`.col-node-${i}`).forEach(el => {
      el.style.display = hidden ? 'none' : '';
    });
    document.querySelectorAll(`.node-chip[data-idx="${i}"]`).forEach(c => {
      c.classList.toggle('active', !hidden);
    });
  });
}

// ── Parameter table ─────────────────────────────────────────────────────
function renderParamTable(file, idx) {
  const colW = _nodeColWidth();
  let hdrs = `<th class="key-th">Parameter</th>` +
    NODES.map((n, i) => {
      let absent = !file.presentIn.includes(n);
      return `<th class="val-th col-node-${i} ${absent?'absent-node-hdr':''}" data-idx="${i}" style="min-width:${colW}px" title="${esc(NODE_DIRS[n]||n)}">${esc(n)}</th>`;
    }).join('');

  let rows = '';
  if (file.sections && file.sections.length) {
    // KV: one header row per section (merged file order) carrying the section check, then its rows
    let bySection = {};
    file.params.forEach((param, pi) => {
      (bySection[param.section] = bySection[param.section] || []).push(pi);
    });
    file.sections.forEach(sec => {
      // Section-level difference: the section is absent on a node that has the file (base included)
      let secDiff = file.presentIn.some(n => !(sec.present || {})[n]);
      rows += renderSectionDivider(file, idx, sec.name,
                                   NODES.filter(n => (sec.present || {})[n]),
                                   renderSectionCheck(file, sec), secDiff);
      (bySection[sec.name] || []).forEach(pi => { rows += renderRow(file, idx, file.params[pi], pi); });
    });
  } else {
    let prevSec = null;
    file.params.forEach((param, pi) => {
      if (param.section && param.section !== 'DEFAULT' && param.section !== prevSec) {
        prevSec = param.section;
        // Nodes that have params in this section (non-null value)
        let nodesWithSection = NODES.filter(n =>
          (file.params || []).some(p => p.section === param.section &&
            p.values && p.values[n] !== null && p.values[n] !== undefined)
        );
        rows += renderSectionDivider(file, idx, param.section, nodesWithSection, '');
      }
      rows += renderRow(file, idx, param, pi);
    });
  }

  const selector = renderNodeSelector();
  const tableId  = `ptbl-${idx}`;
  const table = `<table class="audit-table param-table" id="${tableId}">
    <thead><tr>${hdrs}</tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
  // Phase 4.4 + U-16: initialise column resize and global width after rendering (next tick)
  setTimeout(() => { initColResize(tableId); _initColWidthControls(); }, 0);
  // Note: caller (renderFilePanel) already wraps tableHtml in .table-wrap, so return unwrapped
  return selector + table;
}

function renderSectionDivider(file, idx, secName, nodesWithSection, checkHtml, secDiff) {
  let nodesMissingSection = NODES.filter(n =>
    file.presentIn.includes(n) && !nodesWithSection.includes(n)
  );

  let controls = '';
  // Skip/Unskip section buttons
  controls += `<button class="sec-skip-btn" onclick="skipSection(${idx},'${esj(secName)}')" title="Skip all params in this section">&#10006; Skip section</button>`;
  controls += `<button class="sec-skip-btn" style="background:#90a4ae" onclick="unskipSection(${idx},'${esj(secName)}')" title="Unskip all params in this section">&#8635; Unskip section</button>`;

  // Add-from-node buttons for nodes that have this section
  if (nodesMissingSection.length > 0 && nodesWithSection.length > 0) {
    nodesWithSection.forEach(srcNode => {
      controls += `<button class="sec-addfrom-btn" onclick="addSectionFromNode(${idx},'${esj(secName)}','${esj(srcNode)}')" title="Copy all params in this section from ${srcNode} to nodes that lack them">Add from ${esc(srcNode)}</button>`;
    });
  }

  let label = secName === 'DEFAULT' ? '(no section)' : secName;
  return `<tr class="section-divider" data-sec-diff="${secDiff ? '1' : '0'}">
    <td colspan="${NODES.length + 1}">
      <span class="section-divider-controls">${controls}</span>
      ${esc(label)}${checkHtml}
    </td></tr>`;
}

// Section check: base node's param count, then per other node match/differ/missing/extra or absence
function renderSectionCheck(file, sec) {
  let parts = [];
  let fallback = NODES[0] !== sec.base && !file.presentIn.includes(NODES[0])
    ? ` (${esc(NODES[0])}: file absent)` : '';
  if (sec.baseCount === null || sec.baseCount === undefined) {
    parts.push(`<span class="sec-chk-absent">base ${esc(sec.base)}${fallback}: section absent</span>`);
  } else {
    parts.push(`<span class="sec-chk-base">base ${esc(sec.base)}${fallback}: ${sec.baseCount} param(s)</span>`);
  }
  file.presentIn.filter(n => n !== sec.base).forEach(n => {
    if (!(sec.present || {})[n]) {
      parts.push(`<span class="sec-chk-absent">${esc(n)}: section absent</span>`);
      return;
    }
    let c = (sec.counts || {})[n];
    if (!c) {
      parts.push(`<span class="sec-chk-base">${esc(n)}: ${(sec.paramCounts || {})[n] || 0} param(s)</span>`);
      return;
    }
    let bad = c.differ || c.missing || c.extra;
    parts.push(`<span class="${bad ? 'sec-chk-bad' : 'sec-chk-ok'}">${esc(n)}: ${c.match} match &middot; ${c.differ} differ &middot; ${c.missing} missing${c.extra ? ` &middot; +${c.extra} extra` : ''}</span>`);
  });
  return `<div class="sec-chk">${parts.join('')}</div>`;
}

function renderRow(file, idx, param, pi) {
  let hasPend     = NODES.some(n => getPending(idx, param.compound, n) !== undefined);
  let isSkip      = isSkipped(idx, param.compound);
  let isExpDiff   = param.hasMismatch && _isExpectedDiff(param);
  let cls = 'param-row';
  if (isSkip)                    cls += ' skipped-row';
  else if (hasPend)              cls += ' has-pending';
  else if (param.isLogicalDiff)  cls += ' logical-diff-row';
  else if (isExpDiff)            cls += ' expected-diff-row';
  else if (param.hasMismatch)    cls += ' mismatch-row';

  let revertAllBtn = hasPend
    ? `<button class="revert-all-btn" onclick="revertAll(${idx},'${esj(param.compound)}',${pi})">&#8617; Revert all</button>`
    : '';

  // Skip / Unskip button (only on mismatch / expected-diff rows)
  let skipBtn = '';
  if (param.hasMismatch || isExpDiff) {
    skipBtn = isSkip
      ? `<button class="unskip-btn" onclick="unskipRow(${idx},'${esj(param.compound)}',${pi})">&#8635; Unskip</button>`
      : `<button class="skip-btn"   onclick="skipRow(${idx},'${esj(param.compound)}',${pi})">&#10006; Skip</button>`;
  }

  let skippedLbl = isSkip ? `<span class="skipped-lbl">[Skipped]</span>` : '';
  let logicalLbl = param.isLogicalDiff
    ? `<span class="logical-lbl">&#126; expected node-specific</span>` : '';
  let expDiffLbl = isExpDiff && !param.isLogicalDiff
    ? `<span class="expected-diff-lbl">&#126; instance-specific value</span>` : '';

  let cells = NODES.map((n, ni) => renderCell(file, idx, param, pi, n, ni, isExpDiff)).join('');
  return `<tr class="${cls}" data-pi="${pi}" data-compound="${esa(param.compound)}"
          data-logical="${param.isLogicalDiff ? '1' : '0'}"
          data-exp-diff="${isExpDiff ? '1' : '0'}">
    <td class="key-cell">${esc(param.key)}${logicalLbl}${expDiffLbl}${skippedLbl}${skipBtn}${revertAllBtn}</td>${cells}</tr>`;
}

function renderErrorFile(file) {
  return `<div style="padding:20px">
    <div style="background:#ffebee;border:1px solid #ffcdd2;border-radius:4px;padding:14px 18px">
      <strong style="color:#c62828">&#9888; Processing error</strong><br>
      <span style="font-size:12px;color:#555">${esc((file.warnings||[]).join('; '))}</span>
    </div>
  </div>`;
}

function renderCell(file, idx, param, pi, node, nodeIdx, isExpDiff) {
  let isPresent   = file.presentIn.includes(node);
  let origVal     = (param.values||{})[node];
  let pendVal     = getPending(idx, param.compound, node);
  let effVal      = pendVal !== undefined ? pendVal : origVal;
  let isCommented = (param.commented||{})[node];
  let oid         = `ow-${idx}-${pi}-${eid(node)}`;
  let colCls      = nodeIdx !== undefined ? ` col-node-${nodeIdx}` : '';

  if (!isPresent)
    return `<td class="file-absent-cell${colCls}" data-idx="${nodeIdx}"><span class="absent-lbl">FILE ABSENT</span></td>`;

  if ((origVal === null || origVal === undefined) && pendVal === undefined) {
    return `<td class="key-missing-cell${colCls}" data-idx="${nodeIdx}">
      <span class="missing-lbl">&mdash; missing</span>
      <div><button class="add-btn"
        onclick="addKey(${idx},'${esj(param.compound)}','${esj(node)}',${pi})">+ Add</button></div>
    </td>`;
  }

  let cls = `val-cell${colCls}`;
  if (pendVal !== undefined)      cls += ' cell-pending';
  else if (isExpDiff)             cls += ' cell-expected-diff';
  else if (param.hasMismatch)     cls += ' cell-mismatch';

  let valDisplay = '';
  if (pendVal !== undefined) {
    let origStr = (origVal !== null && origVal !== undefined)
      ? esc(String(origVal)) : '<em>missing</em>';
    valDisplay = `<span class="orig-struck">${origStr}</span> <span class="new-val">${esc(String(pendVal))}</span>`;
  } else if ((param.dupValues || {})[node]) {
    // Duplicate in section: every active value with its source line
    let lines = (param.lines || {})[node] || [];
    valDisplay = param.dupValues[node].map((v, i) =>
      `<div class="dup-val">${esc(String(v))} <span class="dup-line">L${lines[i] !== undefined ? lines[i] : '?'}</span></div>`
    ).join('') + `<span class="dup-tag">duplicate — L${lines.length ? lines[lines.length - 1] : '?'} value used</span>`;
  } else {
    valDisplay = esc(String(effVal !== null && effVal !== undefined ? effVal : ''));
    if (isCommented) valDisplay = `<span style="color:#888">#${valDisplay}</span>`;
  }

  let actBtns = '';
  if (param.hasMismatch || pendVal !== undefined) {
    let revertBtn = pendVal !== undefined
      ? `<button class="revert-btn" onclick="revertNode(${idx},'${esj(param.compound)}','${esj(node)}',${pi})">&#8617;</button>`
      : '';
    let effDisplay = esa(String(effVal !== null && effVal !== undefined ? effVal : ''));
    actBtns = `<div class="cell-actions">
      <button class="use-btn"      onclick="useForAll(${idx},'${esj(param.compound)}','${esj(node)}',${pi})">Use for all</button>
      <button class="override-btn" onclick="showOverride(${idx},'${esj(param.compound)}','${esj(node)}',${pi})">Override</button>
      ${revertBtn}
    </div>
    <div class="override-wrap" id="${oid}">
      <input class="override-input" type="text" value="${effDisplay}"
             id="oi-${oid}" placeholder="Enter new value..."
             onkeydown="if(event.key==='Enter'){applyOverride(${idx},'${esj(param.compound)}','${esj(node)}',${pi});} if(event.key==='Escape'){cancelOverride('${oid}');}">
      <div class="override-actions">
        <button class="apply-btn"  onclick="applyOverride(${idx},'${esj(param.compound)}','${esj(node)}',${pi})">Apply</button>
        <button class="cancel-btn" onclick="cancelOverride('${oid}')">Cancel</button>
        <span class="override-hint">Enter &#9166; to apply &nbsp; Esc to cancel</span>
      </div>
    </div>`;
  }

  return `<td class="${cls}" data-idx="${nodeIdx}"><div class="val-display">${valDisplay}</div>${actBtns}</td>`;
}

// ── Actions ─────────────────────────────────────────────────────────────

function useForAll(fileIdx, compound, sourceNode, pi) {
  let file      = FILES[fileIdx];
  let param     = file.params[pi];
  let sourceVal = getPending(fileIdx, compound, sourceNode);
  if (sourceVal === undefined) sourceVal = (param.values||{})[sourceNode];
  if (sourceVal === null || sourceVal === undefined) return;

  NODES.forEach(n => {
    if (!file.presentIn.includes(n)) return;
    let cur = getPending(fileIdx, compound, n);
    if (cur === undefined) cur = (param.values||{})[n];
    if (String(cur) !== String(sourceVal))
      _setPendingLogged(fileIdx, compound, n, String(sourceVal), param);
  });
  refreshRow(fileIdx, pi);
  refreshDlBtns(fileIdx);
  refreshSidebarBadge(fileIdx);
  updateChangeCounter();
}

function showOverride(fileIdx, compound, node, pi) {
  // BUG-05 / req(c): close all other open overrides first
  document.querySelectorAll('.override-wrap.open').forEach(el => el.classList.remove('open'));
  let ow = document.getElementById(`ow-${fileIdx}-${pi}-${eid(node)}`);
  if (ow) {
    ow.classList.add('open');
    let inp = ow.querySelector('.override-input');
    if (inp) { inp.focus(); inp.select(); }
  }
}

function cancelOverride(oid) {
  let ow = document.getElementById(oid);
  if (ow) ow.classList.remove('open');
}

// BUG-05: skip pending if new value equals original
function applyOverride(fileIdx, compound, node, pi) {
  let oid = `ow-${fileIdx}-${pi}-${eid(node)}`;
  let inp = document.getElementById(`oi-${oid}`);
  if (!inp) return;
  let newVal   = inp.value;
  let param    = FILES[fileIdx].params[pi];
  let origVal  = (param.values||{})[node];
  let origStr  = origVal !== null && origVal !== undefined ? String(origVal) : null;

  if (newVal === origStr) {
    // BUG-05: revert instead of setting a no-op pending
    clearPendingLogged(fileIdx, compound, node, param);
  } else {
    _setPendingLogged(fileIdx, compound, node, newVal, param);
  }
  cancelOverride(oid);
  refreshRow(fileIdx, pi);
  refreshDlBtns(fileIdx);
  refreshSidebarBadge(fileIdx);
  updateChangeCounter();
}

function revertNode(fileIdx, compound, node, pi) {
  let param = FILES[fileIdx].params[pi];
  clearPendingLogged(fileIdx, compound, node, param);
  refreshRow(fileIdx, pi);
  refreshDlBtns(fileIdx);
  refreshSidebarBadge(fileIdx);
  updateChangeCounter();
}

function revertAll(fileIdx, compound, pi) {
  let param = FILES[fileIdx].params[pi];
  NODES.forEach(n => clearPendingLogged(fileIdx, compound, n, param));
  refreshRow(fileIdx, pi);
  refreshDlBtns(fileIdx);
  refreshSidebarBadge(fileIdx);
  updateChangeCounter();
}

function addKey(fileIdx, compound, node, pi) {
  let file  = FILES[fileIdx];
  let param = file.params[pi];
  let firstVal = '';
  for (let n of file.presentIn) {
    let v = (param.values||{})[n];
    if (v !== null && v !== undefined) { firstVal = String(v); break; }
  }
  _setPendingLogged(fileIdx, compound, node, firstVal, param);
  refreshRow(fileIdx, pi);
  refreshDlBtns(fileIdx);
  refreshSidebarBadge(fileIdx);
  updateChangeCounter();
  setTimeout(() => showOverride(fileIdx, compound, node, pi), 0);
}

// ── Pending state with change-log tracking ────────────────────────────

function getPending(fileIdx, compound, node) {
  return pending[fileIdx] && pending[fileIdx][compound]
    ? pending[fileIdx][compound][node]
    : undefined;
}

function _setPendingLogged(fileIdx, compound, node, value, param) {
  let file    = FILES[fileIdx];
  let origVal = (param.values||{})[node];
  let isAdd   = (origVal === null || origVal === undefined);
  let action  = isAdd ? 'added' : 'modified';

  // Remove any existing change-log entry for this cell before adding new
  _removeChangeLogEntry(fileIdx, compound, node);

  if (!pending[fileIdx]) pending[fileIdx] = {};
  if (!pending[fileIdx][compound]) pending[fileIdx][compound] = {};
  pending[fileIdx][compound][node] = value;

  changeLog.push({
    ts:        new Date().toISOString(),
    action,
    fileIdx,
    file:      file.path,
    compound,
    key:       param.key,
    section:   param.section,
    node,
    orig:      isAdd ? null : (origVal !== null && origVal !== undefined ? String(origVal) : null),
    corrected: value,
  });
  _saveState();
}

function clearPendingLogged(fileIdx, compound, node, param) {
  _removeChangeLogEntry(fileIdx, compound, node);
  if (pending[fileIdx] && pending[fileIdx][compound]) {
    delete pending[fileIdx][compound][node];
    if (!Object.keys(pending[fileIdx][compound]).length) delete pending[fileIdx][compound];
    if (!Object.keys(pending[fileIdx]).length) delete pending[fileIdx];
  }
  _saveState();
}

function _removeChangeLogEntry(fileIdx, compound, node) {
  let idx = changeLog.findIndex(e => e.fileIdx === fileIdx && e.compound === compound && e.node === node);
  if (idx >= 0) changeLog.splice(idx, 1);
}

function _anyPendingForFile(fileIdx) {
  return !!(pending[fileIdx] && Object.keys(pending[fileIdx]).length > 0);
}
function _anyPendingForFileNode(fileIdx, node) {
  return !!(pending[fileIdx] &&
    Object.values(pending[fileIdx]).some(m => m[node] !== undefined));
}

// ── Change counter (header badge) ────────────────────────────────────
function updateChangeCounter() {
  let el = document.getElementById('change-count');
  if (!el) return;
  let n = changeLog.length;
  el.textContent = n;
  el.className   = 'change-counter' + (n > 0 ? ' has-changes' : '');
}

// ── Change log modal ─────────────────────────────────────────────────
function openChangeLog() {
  renderChangeLogModal();
  let m = document.getElementById('cl-modal');
  if (m) m.classList.add('open');
}
function closeChangeLog() {
  let m = document.getElementById('cl-modal');
  if (m) m.classList.remove('open');
}
function renderChangeLogModal() {
  let body = document.getElementById('cl-modal-body');
  if (!body) return;
  if (!changeLog.length) {
    body.innerHTML = `<div class="cl-empty">No changes yet. Use "Use for all", "Override", or "+ Add" to record changes.</div>`;
    return;
  }
  let rows = changeLog.map((e, i) => {
    let origCell    = e.orig !== null ? `<span class="cl-orig">${esc(e.orig)}</span>` : `<em style="color:#aaa">missing</em>`;
    let newCell     = `<span class="cl-new">${esc(e.corrected)}</span>`;
    let actionBadge = `<span class="cl-action cl-${esc(e.action)}">${e.action.toUpperCase()}</span>`;
    let tsShort     = e.ts.replace('T',' ').substring(0,19);
    return `<tr>
      <td><span class="cl-file">${esc(e.file)}</span></td>
      <td><span class="cl-node">${esc(e.node)}</span></td>
      <td><span class="cl-key">${esc(e.key)}</span><br><small style="color:#888">${esc(e.section||'DEFAULT')}</small></td>
      <td>${origCell}</td>
      <td>${newCell}</td>
      <td>${actionBadge}</td>
      <td style="font-size:10px;color:#aaa;white-space:nowrap">${tsShort}</td>
    </tr>`;
  }).join('');
  body.innerHTML = `<table class="cl-table">
    <thead><tr>
      <th>File</th><th>Node</th><th>Key</th>
      <th>Original</th><th>Corrected</th><th>Action</th><th>Time</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// ── Export Patch JSON (MISS-02) ───────────────────────────────────────
function exportPatch() {
  // Collect all skipped entries across all files
  let skippedArr = [];
  Object.keys(skipped).forEach(fi => {
    Object.keys(skipped[fi]).forEach(compound => {
      let file = FILES[parseInt(fi)];
      skippedArr.push({file: file.path, compound});
    });
  });

  if (!changeLog.length && !skippedArr.length) {
    alert('No changes or skips to export.'); return;
  }
  let patch = {
    audit_run:   RUN_AT,
    exported_at: new Date().toISOString(),
    node_dirs:   NODE_DIRS,
    output_dir:  OUTPUT_DIR,
    run_dir:     AUDIT_DATA.runDir || '',
    changes:     changeLog.map(e => ({
      file:      e.file,
      file_type: FILES[e.fileIdx].type,
      node:      e.node,
      compound:  e.compound,
      key:       e.key,
      section:   e.section,
      original:  e.orig,
      corrected: e.corrected,
      action:    e.action,
    })),
    skipped: skippedArr,
  };
  let ts    = new Date().toISOString().replace(/[:.]/g,'').substring(0,15);
  _blobDownload(JSON.stringify(patch, null, 2), `audit_patch_${ts}.json`, 'application/json');
}

// ── Export human-readable change log ─────────────────────────────────
function exportChangeLogText() {
  if (!changeLog.length) { alert('No changes to export.'); return; }
  let lines = [
    'ConfigMergeTool Audit — Change Log',
    `Audit run : ${RUN_AT}`,
    `Exported  : ${new Date().toISOString()}`,
    `Changes   : ${changeLog.length}`,
    '',
    '─'.repeat(100),
  ];
  changeLog.forEach((e, i) => {
    lines.push(`[${String(i+1).padStart(3,'0')}] ${e.action.toUpperCase().padEnd(8)} ${e.ts.replace('T',' ').substring(0,19)}`);
    lines.push(`      File    : ${e.file}`);
    lines.push(`      Node    : ${e.node}`);
    lines.push(`      Key     : ${e.section ? e.section + '|' : ''}${e.key}`);
    lines.push(`      Original: ${e.orig !== null ? e.orig : '<missing>'}`);
    lines.push(`      Fixed   : ${e.corrected}`);
    lines.push('');
  });
  let ts = new Date().toISOString().replace(/[:.]/g,'').substring(0,15);
  _blobDownload(lines.join('\n'), `audit_changelog_${ts}.txt`, 'text/plain');
}

function _blobDownload(content, filename, mime) {
  let blob = new Blob([content], {type: mime});
  let url  = URL.createObjectURL(blob);
  let a    = Object.assign(document.createElement('a'), {href: url, download: filename});
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// ── Row refresh ───────────────────────────────────────────────────────
function refreshRow(fileIdx, pi) {
  let file  = FILES[fileIdx];
  let param = file.params[pi];
  // Try both table id formats (ptbl- for kv/json, txt- for text/xml)
  let tbl = document.getElementById(`ptbl-${fileIdx}`) || document.getElementById(`txt-${fileIdx}`);
  if (!tbl) return;
  let row = tbl.querySelector(`tr[data-pi="${pi}"]`);
  if (!row) return;
  let tmp = document.createElement('tbody');
  tmp.innerHTML = renderRow(file, fileIdx, param, pi);
  row.parentNode.replaceChild(tmp.firstElementChild, row);
  applyDiffsFilter();
}

// ── Diffs filter ──────────────────────────────────────────────────────
let showExpectedDiffs = true;
let showLogicalDiffs  = true;

function toggleDiffsOnly(checked) {
  showDiffsOnly = checked;
  applyDiffsFilter();
}

function toggleExpectedDiffsVisible(checked) {
  showExpectedDiffs = checked;
  applyDiffsFilter();
}

function toggleLogicalVisible(checked) {
  showLogicalDiffs = checked;
  applyDiffsFilter();
}

function applyDiffsFilter() {
  if (currentFileIdx < 0) return;
  let tbl = document.getElementById(`ptbl-${currentFileIdx}`)
         || document.getElementById(`txt-${currentFileIdx}`);
  if (!tbl) return;
  let rows = Array.from(tbl.querySelectorAll('tbody tr'));
  rows.forEach(row => {
    if (!row.classList.contains('param-row')) return;
    let isMM      = row.classList.contains('mismatch-row');
    let isPend    = row.classList.contains('has-pending');
    let isExpD    = row.dataset.expDiff === '1';
    let isLogical = row.dataset.logical === '1';
    // Visibility rules:
    // 1. If showDiffsOnly: hide matched rows (unless pending)
    // 2. If !showExpectedDiffs: hide expected-diff rows
    // 3. If !showLogicalDiffs: hide logical-diff rows
    let vis = true;
    if (showDiffsOnly && !isMM && !isPend && !isExpD) vis = false;
    if (!showExpectedDiffs && isExpD && !isPend) vis = false;
    if (!showLogicalDiffs && isLogical && !isPend) vis = false;
    row.style.display = vis ? '' : 'none';
  });
  rows.forEach((row, i) => {
    if (!row.classList.contains('section-divider')) return;
    let anyVis = false, hasRows = false;
    for (let j = i + 1; j < rows.length; j++) {
      if (rows[j].classList.contains('section-divider')) break;
      hasRows = true;
      if (rows[j].style.display !== 'none') { anyVis = true; break; }
    }
    // Keep headers whose section check flags a difference, and empty sections when not filtering
    let keep = anyVis || row.dataset.secDiff === '1' || (!hasRows && !showDiffsOnly);
    row.style.display = keep ? '' : 'none';
  });
}

// ── Skipped files panel ───────────────────────────────────────────────
function _copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    let orig = btn.textContent;
    btn.textContent = '✓ Copied';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1800);
  }).catch(() => {
    // Fallback for environments without clipboard API
    let ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch(e) {}
    document.body.removeChild(ta);
    let orig = btn.textContent;
    btn.textContent = '✓ Copied'; btn.disabled = true;
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1800);
  });
}

function renderSkippedPanel() {
  let panel = document.getElementById('skipped-panel');
  if (!panel) return;
  let total = SKIPPED_BACKUPS.length + FILTERED_FILES.length;
  if (!total) { panel.style.display = 'none'; return; }

  let mkRow = (r, ruleType) => {
    // Generate include rule: for backup-detected files, suggest a no_skip_files entry;
    // for filter-excluded files, suggest removing the filter or adding an include override
    let rule = ruleType === 'backup'
      ? JSON.stringify({"no_skip_files": [r.path]}, null, 2)
      : JSON.stringify({"include": [r.path]}, null, 2);
    let ruleLabel = ruleType === 'backup' ? 'no_skip rule' : 'include rule';
    return `<tr>
      <td>${esc(r.path)}</td>
      <td>${esc(r.reason)}</td>
      <td style="color:#888">${esc(r.base_dir||'')}</td>
      <td><button class="skipped-copy-btn" onclick="_copyToClipboard(${JSON.stringify(rule)}, this)">&#128203; Copy ${ruleLabel}</button></td>
    </tr>`;
  };

  let mkTable = (rows, ruleType) => {
    if (!rows.length) return '<p style="padding:8px 16px;color:#999;font-size:11px">None.</p>';
    return `<table class="skipped-table">
      <thead><tr><th>Path</th><th>Reason</th><th>Base Dir</th><th>Action</th></tr></thead>
      <tbody>${rows.map(r => mkRow(r, ruleType)).join('')}</tbody>
    </table>`;
  };

  panel.querySelector('.skipped-count').textContent = total + ' file' + (total!==1?'s':'');
  let body = panel.querySelector('.skipped-panel-body');
  let html = '';
  if (SKIPPED_BACKUPS.length) {
    html += `<div class="skipped-subsection">
      <div class="skipped-subsec-hdr">Backup files auto-detected (${SKIPPED_BACKUPS.length})</div>
      ${mkTable(SKIPPED_BACKUPS, 'backup')}
    </div>`;
  }
  if (FILTERED_FILES.length) {
    html += `<div class="skipped-subsection">
      <div class="skipped-subsec-hdr">Excluded by filter (${FILTERED_FILES.length})</div>
      ${mkTable(FILTERED_FILES, 'filter')}
    </div>`;
  }
  body.innerHTML = html;
}

function toggleSkippedPanel() {
  let body = document.getElementById('skipped-panel-body');
  let chev = document.getElementById('skipped-chev');
  if (!body) return;
  let open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (chev) chev.innerHTML = open ? '&#9654;' : '&#9660;';
}

// ── Report errors panel ───────────────────────────────────────────────
function renderErrorsPanel() {
  let panel = document.getElementById('errors-panel');
  if (!panel) return;
  if (!RENDER_ERRORS.length) { panel.style.display = 'none'; return; }
  panel.querySelector('.errors-count').textContent = RENDER_ERRORS.length + ' file' + (RENDER_ERRORS.length!==1?'s':'');
  let body = panel.querySelector('.errors-table tbody');
  body.innerHTML = RENDER_ERRORS.map(e =>
    `<tr>
      <td class="mono">${esc(e.path)}</td>
      <td class="mono" style="color:#c62828">${esc(e.error)}</td>
      <td style="font-size:11px;color:#666">${(e.presentIn||[]).map(esc).join(', ')}</td>
    </tr>`
  ).join('');
}

function toggleErrorsPanel() {
  let body = document.getElementById('errors-panel-body');
  let chev = document.getElementById('errors-chev');
  if (!body) return;
  let open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (chev) chev.innerHTML = open ? '&#9654;' : '&#9660;';
}

// ── Tab navigation ────────────────────────────────────────────────────
function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabName);
  });
  // Show/hide panels
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + tabName);
  });
  // Lazy-render sub-tab content on first visit
  if (tabName === 'skipped') _renderSkippedTab();
  if (tabName === 'filtered') _renderFilteredTab();
}

function _mkSkippedTable(rows, ruleType) {
  if (!rows.length) return '<p class="tab-empty">None.</p>';
  let mkRow = r => {
    let rule = ruleType === 'backup'
      ? JSON.stringify({"no_skip_files": [r.path]}, null, 2)
      : JSON.stringify({"include": [r.path]}, null, 2);
    let ruleLabel = ruleType === 'backup' ? 'no_skip rule' : 'include rule';
    return `<tr>
      <td style="font-family:monospace">${esc(r.path)}</td>
      <td>${esc(r.reason)}</td>
      <td style="color:#888;font-size:11px">${esc(r.base_dir||'')}</td>
      <td><button class="skipped-copy-btn"
            onclick="_copyToClipboard(${JSON.stringify(rule)}, this)">&#128203; Copy ${ruleLabel}</button></td>
    </tr>`;
  };
  return `<table class="skipped-table">
    <thead><tr><th>Path</th><th>Reason</th><th>Base Dir</th><th>Action</th></tr></thead>
    <tbody>${rows.map(mkRow).join('')}</tbody>
  </table>`;
}

let _skippedTabRendered  = false;
let _filteredTabRendered = false;

function _renderSkippedTab() {
  if (_skippedTabRendered) return;
  _skippedTabRendered = true;
  let el = document.getElementById('skipped-tab-body');
  if (!el) return;
  if (!SKIPPED_BACKUPS.length) {
    el.innerHTML = '<p class="tab-empty">No backup files were auto-detected and skipped.</p>';
    return;
  }
  el.innerHTML = _mkSkippedTable(SKIPPED_BACKUPS, 'backup');
}

function _renderFilteredTab() {
  if (_filteredTabRendered) return;
  _filteredTabRendered = true;
  let el = document.getElementById('filtered-tab-body');
  if (!el) return;
  if (!FILTERED_FILES.length) {
    el.innerHTML = '<p class="tab-empty">No files were excluded by the filter.</p>';
    return;
  }
  el.innerHTML = _mkSkippedTable(FILTERED_FILES, 'filter');
}

// ── Export diffs as CSV ───────────────────────────────────────────────
// ── Download ──────────────────────────────────────────────────────────
function downloadConfig(fileIdx, node, targetPath) {
  let file    = FILES[fileIdx];
  let content = reconstructContent(fileIdx, file, node);
  if (content === null) { alert('No content available to download.'); return; }
  // Use just the filename for the browser download; target path shown in tooltip
  let fname = file.path.split('/').pop();
  _blobDownload(content, fname, 'text/plain');
  // If output_dir is configured, show the target path as a confirmation
  if (targetPath) {
    console.log('[ConfigMergeTool] Save to:', targetPath);
  }
}

function reconstructContent(fileIdx, file, node) {
  let changes     = pending[fileIdx] || {};
  let fileSkipped = skipped[fileIdx]  || {};
  let raw         = (file.rawContent||{})[node];
  if (file.type === 'kv')   return reconstructKV(file, node, changes, raw, fileSkipped);
  if (file.type === 'json') return reconstructJSON(file, node, changes, raw, fileSkipped);
  return raw || null;
}

function reconstructKV(file, node, changes, raw, fileSkipped) {
  fileSkipped = fileSkipped || {};
  if (!raw) {
    let bySec = {};
    (file.params||[]).forEach(p => {
      if (fileSkipped[p.compound]) return;  // exclude skipped
      let v = changes[p.compound] ? changes[p.compound][node] : undefined;
      if (v === undefined) return;
      let sec = p.section || 'DEFAULT';
      if (!bySec[sec]) bySec[sec] = [];
      bySec[sec].push({key: p.key, value: v});
    });
    let lines = [];
    Object.entries(bySec).forEach(([sec, params]) => {
      lines.push('');
      if (sec !== 'DEFAULT') lines.push(sec);
      params.forEach(({key, value}) => lines.push(`${key}=${value}`));
    });
    return lines.join('\n') + '\n';
  }

  let lines          = raw.split('\n');
  let currentSection = 'DEFAULT';
  let modified       = {};

  for (let i = 0; i < lines.length; i++) {
    let line     = lines[i];
    let stripped = line.trim();
    let sm = stripped.match(/^\[([^\]]+)\]$/);
    if (sm) { currentSection = '[' + sm[1] + ']'; continue; }
    if (stripped.startsWith('#') || stripped.startsWith('!') || !stripped) continue;

    let ei = stripped.indexOf('='), ci = stripped.indexOf(':');
    let di = -1, delim = '=';
    if (ei >= 0 && (ci < 0 || ei <= ci)) { di = ei; delim = '='; }
    else if (ci >= 0) { di = ci; delim = ':'; }
    if (di < 0) continue;

    let key = stripped.substring(0, di).trim();
    if (!key) continue;
    // NOTE: keys with embedded whitespace (e.g. shell-script lines like
    // "nohup java -Dapp=value") are valid in the audit engine — do NOT skip them.

    let compound    = currentSection + '|' + key;
    if (fileSkipped[compound]) continue;  // exclude skipped
    let nodeChanges = changes[compound];
    if (nodeChanges && nodeChanges[node] !== undefined) {
      let lineDelim = line.indexOf(delim);
      lines[i]      = line.substring(0, lineDelim + 1) + nodeChanges[node];
      modified[compound] = true;
    }
  }

  let addBySec = {};
  (file.params||[]).forEach(p => {
    if (fileSkipped[p.compound]) return;  // exclude skipped
    let nodeChanges = changes[p.compound];
    if (!modified[p.compound] && nodeChanges && nodeChanges[node] !== undefined) {
      let sec = p.section || 'DEFAULT';
      if (!addBySec[sec]) addBySec[sec] = [];
      addBySec[sec].push({key: p.key, value: nodeChanges[node]});
    }
  });
  if (Object.keys(addBySec).length) {
    lines.push('');
    Object.entries(addBySec).forEach(([sec, params]) => {
      if (sec !== 'DEFAULT') lines.push(sec);
      params.forEach(({key, value}) => lines.push(`${key}=${value}`));
    });
  }

  return lines.join('\n');
}

function reconstructJSON(file, node, changes, raw, fileSkipped) {
  fileSkipped = fileSkipped || {};
  if (!raw) return null;
  try {
    let obj = JSON.parse(raw);
    Object.entries(changes).forEach(([compound, byNode]) => {
      if (fileSkipped[compound]) return;  // exclude skipped
      if (byNode[node] === undefined) return;
      let parts = compound.split('.');
      let cur   = obj;
      for (let i = 0; i < parts.length - 1; i++) {
        if (cur && typeof cur === 'object' && parts[i] in cur) cur = cur[parts[i]];
        else return;
      }
      if (cur && typeof cur === 'object') cur[parts[parts.length - 1]] = byNode[node];
    });
    return JSON.stringify(obj, null, 2);
  } catch(e) { return raw; }
}

function refreshDlBtns(fileIdx) {
  let file    = FILES[fileIdx];
  let dlGroup = document.querySelector('.dl-group');
  if (!dlGroup) return;
  dlGroup.innerHTML = NODES
    .filter(n => file.presentIn.includes(n) || _anyPendingForFileNode(fileIdx, n))
    .map(n => `<button class="dl-btn" onclick="downloadConfig(${fileIdx},'${esj(n)}')">&#11015; ${esc(n)}</button>`)
    .join('');
}

// ── Utility ───────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function esj(s) { return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function esa(s) { return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function eid(s) { return String(s).replace(/[^a-zA-Z0-9]/g,'_'); }

// ── PHASE 4.2: Skip row ───────────────────────────────────────────────
// skipped[fileIdx][compound] = true
const skipped = {};

function isSkipped(fileIdx, compound) {
  return !!(skipped[fileIdx] && skipped[fileIdx][compound]);
}

function skipRow(fileIdx, compound, pi) {
  if (!skipped[fileIdx]) skipped[fileIdx] = {};
  skipped[fileIdx][compound] = true;
  refreshRow(fileIdx, pi);
  refreshSidebarBadge(fileIdx);
  _buildMismatchIndex();
  _saveState();
}

function unskipRow(fileIdx, compound, pi) {
  if (skipped[fileIdx]) delete skipped[fileIdx][compound];
  refreshRow(fileIdx, pi);
  refreshSidebarBadge(fileIdx);
  _buildMismatchIndex();
  _saveState();
}

function skipSection(fileIdx, sectionName) {
  let file = FILES[fileIdx];
  (file.params || []).forEach((p, pi) => {
    if (p.section === sectionName && !isSkipped(fileIdx, p.compound)) {
      skipParam(fileIdx, p.compound, pi);
    }
  });
}

function unskipSection(fileIdx, sectionName) {
  let file = FILES[fileIdx];
  (file.params || []).forEach((p, pi) => {
    if (p.section === sectionName && isSkipped(fileIdx, p.compound)) {
      unskipRow(fileIdx, p.compound, pi);
    }
  });
}

function skipParam(fileIdx, compound, pi) {
  if (!skipped[fileIdx]) skipped[fileIdx] = {};
  skipped[fileIdx][compound] = true;
  refreshRow(fileIdx, pi);
  refreshSidebarBadge(fileIdx);
  _buildMismatchIndex();
  _saveState();
}

function addSectionFromNode(fileIdx, sectionName, sourceNode) {
  let file = FILES[fileIdx];
  (file.params || []).forEach((p, pi) => {
    if (p.section !== sectionName) return;
    let sourceVal = getPending(fileIdx, p.compound, sourceNode);
    if (sourceVal === undefined) sourceVal = (p.values || {})[sourceNode];
    if (sourceVal === null || sourceVal === undefined) return;
    NODES.forEach(targetNode => {
      if (targetNode === sourceNode) return;
      if (!file.presentIn.includes(targetNode)) return;
      let curVal = getPending(fileIdx, p.compound, targetNode);
      if (curVal === undefined) curVal = (p.values || {})[targetNode];
      // Only set for nodes that lack the param (null/undefined)
      if (curVal === null || curVal === undefined) {
        _setPendingLogged(fileIdx, p.compound, targetNode, String(sourceVal), p);
      }
    });
    refreshRow(fileIdx, pi);
  });
  refreshDlBtns(fileIdx);
  refreshSidebarBadge(fileIdx);
  updateChangeCounter();
}

// ── PHASE 4.3: Mismatch navigation ───────────────────────────────────
let _mmIndex = [];    // [{fileIdx, pi}] — all mismatch params in order
let _mmPos   = -1;   // current position in _mmIndex

function _buildMismatchIndex() {
  _mmIndex = [];
  FILES.forEach((f, fi) => {
    (f.params || []).forEach((p, pi) => {
      if (p.hasMismatch && !isSkipped(fi, p.compound)) {
        _mmIndex.push({fileIdx: fi, pi});
      }
    });
  });
  _updateNavCounter();
}

function _updateNavCounter() {
  let el = document.getElementById('mm-nav-counter');
  if (!el) return;
  let total = _mmIndex.length;
  if (total === 0) { el.textContent = 'No mismatches'; return; }
  let pos = _mmPos >= 0 ? _mmPos + 1 : '—';
  el.textContent = `Mismatch ${pos} / ${total}`;
}

function prevMismatch() {
  if (!_mmIndex.length) return;
  _mmPos = _mmPos <= 0 ? _mmIndex.length - 1 : _mmPos - 1;
  _jumpToMismatch(_mmIndex[_mmPos]);
}

function nextMismatch() {
  if (!_mmIndex.length) return;
  _mmPos = (_mmPos + 1) % _mmIndex.length;
  _jumpToMismatch(_mmIndex[_mmPos]);
}

function _jumpToMismatch(entry) {
  if (!entry) return;
  let {fileIdx, pi} = entry;
  if (fileIdx !== currentFileIdx) selectFile(fileIdx);
  _updateNavCounter();
  // Scroll to row and pulse
  setTimeout(() => {
    let tbl = document.getElementById(`ptbl-${fileIdx}`) || document.getElementById(`txt-${fileIdx}`);
    if (!tbl) return;
    let row = tbl.querySelector(`tr[data-pi="${pi}"]`);
    if (!row) return;
    row.scrollIntoView({block:'center', behavior:'smooth'});
    row.classList.remove('mm-nav-pulse');
    void row.offsetWidth; // reflow
    row.classList.add('mm-nav-pulse');
    setTimeout(() => row.classList.remove('mm-nav-pulse'), 900);
  }, fileIdx !== currentFileIdx ? 150 : 0);
}

// ── U-16: Global column width & value wrap ────────────────────────────
function adjustColWidth(delta) {
  _colWidth = Math.max(80, Math.min(1200, (_colWidth || _nodeColWidth()) + delta));
  _applyColWidthToTable();
  let el = document.getElementById('col-width-disp');
  if (el) el.textContent = _colWidth;
  try { localStorage.setItem('cm_col_width', _colWidth); } catch(e) {}
}

function _applyColWidthToTable() {
  // Apply to every val-th in the currently visible table
  document.querySelectorAll('.param-table th.val-th').forEach(th => {
    th.style.width = _colWidth + 'px';
    th.style.minWidth = _colWidth + 'px';
  });
}

function _initColWidthControls() {
  // Sync the display label and wrap input with current state after renderFilePanel
  let disp = document.getElementById('col-width-disp');
  if (disp) disp.textContent = _colWidth || _nodeColWidth();
  let inp = document.getElementById('wrap-chars-inp');
  if (inp) inp.value = _valWrap > 0 ? _valWrap : '';
  _applyColWidthToTable();
}

function _applyWrapCss(chars) {
  if (chars > 0) {
    document.documentElement.style.setProperty('--val-wrap', chars + 'ch');
  } else {
    document.documentElement.style.removeProperty('--val-wrap');
  }
}

function applyWrap(chars) {
  _valWrap = (isNaN(chars) || chars <= 0) ? 0 : chars;
  _applyWrapCss(_valWrap);
  let inp = document.getElementById('wrap-chars-inp');
  if (inp) inp.value = _valWrap > 0 ? _valWrap : '';
  try { localStorage.setItem('cm_val_wrap', _valWrap); } catch(e) {}
}

function clearWrap() {
  applyWrap(0);
}

// ── PHASE 4.4: Resizable columns ─────────────────────────────────────
function initColResize(tableId) {
  let tbl = document.getElementById(tableId);
  if (!tbl) return;
  let lsKey = `cm_col_${tableId}_${currentFileIdx}`;
  let ths   = Array.from(tbl.querySelectorAll('thead th'));

  // Restore saved widths
  try {
    let saved = JSON.parse(localStorage.getItem(lsKey) || 'null');
    if (saved && saved.length === ths.length) {
      ths.forEach((th, i) => { if (saved[i]) th.style.width = saved[i] + 'px'; });
    }
  } catch(e) {}

  ths.forEach((th, i) => {
    th.addEventListener('mousedown', function(e) {
      // Only trigger on the right 5px (resize handle area)
      if (e.offsetX < th.offsetWidth - 5) return;
      e.preventDefault();
      let startX  = e.clientX;
      let startW  = th.offsetWidth;

      function onMove(e2) {
        let newW = Math.max(80, startW + e2.clientX - startX);
        th.style.width = newW + 'px';
      }
      function onUp() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup',   onUp);
        // Persist
        let widths = ths.map(t => t.offsetWidth);
        try { localStorage.setItem(lsKey, JSON.stringify(widths)); } catch(e) {}
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup',   onUp);
    });
  });
}
"""


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialise_result(result: "AuditResult") -> dict:
    files_js = []
    for af in result.files:
        params_js = [
            {
                "compound":      p.compound,
                "section":       p.section,
                "key":           p.key,
                "values":        p.values,
                "commented":     p.commented,
                "hasMismatch":   p.has_mismatch,
                "isLogicalDiff": p.is_logical_diff,
                "lines":         p.lines,
                "dupValues":     p.dup_values,
            }
            for p in af.params
        ]
        sections_js = [
            {
                "name":        s["name"],
                "base":        s["base"],
                "present":     s["present"],
                "baseCount":   s["base_count"],
                "counts":      s["counts"],
                "paramCounts": s["param_counts"],
            }
            for s in af.sections
        ]
        binary_js = None
        if af.file_type == "binary":
            binary_js = {
                node: {
                    "md5":     bi.md5,
                    "size":    bi.size_bytes,
                    "present": bi.present,
                }
                for node, bi in af.binary.items()
            }
        files_js.append({
            "path":            af.rel_path,
            "type":            af.file_type,
            "presentIn":       af.present_in,
            "mismatchCount":   af.mismatch_count,
            "absentCount":     af.absent_count,
            "logicalDiffCount": af.logical_diff_count,
            "params":          params_js,
            "sections":        sections_js,
            "rawContent":      af.raw_content if af.file_type not in ("binary", "error") else {},
            "binary":          binary_js,
            "warnings":        af.warnings,
            "contentSkipped":  af.content_skipped,
            "paramCount":      af.param_count,
            "fileSizes":       af.file_sizes,
        })

    # Skipped-files and error data for the Skipped Files / Report Errors panels
    skipped_js = [
        {"path": e.get("rel_path",""), "reason": e.get("reason",""), "base_dir": e.get("base_dir","")}
        for e in (result.skipped_backups or [])
    ]
    filtered_js = [
        {"path": e.get("rel_path",""), "reason": e.get("reason",""), "base_dir": e.get("base_dir","")}
        for e in (result.filtered_files or [])
    ]
    errors_js = [
        {"path": e.get("rel_path",""), "error": e.get("error",""), "presentIn": e.get("present_in",[])}
        for e in (result.render_errors or [])
    ]

    return {
        "nodes":          result.nodes,
        "nodeDirs":       result.node_dirs,
        "outputDir":      result.output_dir,
        "runDir":         result.run_dir,
        "runAt":          result.run_timestamp,
        "files":          files_js,
        "skippedBackups": skipped_js,
        "filteredFiles":  filtered_js,
        "renderErrors":   errors_js,
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

# Stands in for the AUDIT_DATA JSON while the page template is rendered; never in output.
_DATA_SLOT = "\x00AUDIT_DATA_SLOT\x00"


def _render_html_parts(result: "AuditResult", files_js=None, pagination=None):
    """Render a self-contained audit report as (head, data_js, tail).

    head + data_js + tail is the page.  Kept apart so the (large) page is never
    concatenated in memory: the template holds non-Latin-1 characters, which
    would store the whole joined page at 2 bytes/char (M-2).

    Parameters
    ----------
    files_js:
        Optional pre-serialised list of file dicts.  When None the full result
        is serialised (single-file, no pagination).
    pagination:
        Optional dict with keys ``current`` (1-based), ``total``, ``parts``
        (list of ``{label, url}``).  When provided, a part-navigation bar is
        rendered at the top of the page.
    """
    if files_js is None:
        data = _serialise_result(result)
    else:
        data = {
            "nodes":    result.nodes,
            "nodeDirs": result.node_dirs,
            "runAt":    result.run_timestamp,
            "files":    files_js,
        }
    if pagination:
        data["pagination"] = pagination

    # BUG-A: Raw file content may contain </script> or <script> (any case)
    # inside the JSON blob.  Closing tags must be escaped to prevent premature
    # script-block termination; opening tags must be escaped to keep the HTML
    # sanity checker (and browsers) from treating them as real tag openers.
    # \u003c is a JSON-safe unicode escape that JS evaluates back to '<'.
    data_js = json.dumps(data, ensure_ascii=False, indent=2)
    data_js = re.sub(r'</(script)', r'<\/\1', data_js, flags=re.IGNORECASE)
    data_js = re.sub(r'<(script\b)', r'\\u003c\1', data_js, flags=re.IGNORECASE)

    ts_display = (
        result.run_timestamp[:4]   + "-" +
        result.run_timestamp[4:6]  + "-" +
        result.run_timestamp[6:8]  + " " +
        result.run_timestamp[9:11] + ":" +
        result.run_timestamp[11:13] + ":" +
        result.run_timestamp[13:15]
    )

    node_list    = " &middot; ".join(result.nodes)
    total_files  = len(result.files)
    files_differ = sum(1 for f in result.files if f.mismatch_count > 0)
    total_mm     = result.total_mismatches
    binary_diff  = sum(1 for f in result.files
                       if f.file_type == "binary" and f.mismatch_count > 0)
    files_absent = sum(1 for f in result.files if f.absent_count > 0)
    render_errors_count = len(result.render_errors or [])

    # Warning / error count for summary
    files_with_warnings = sum(1 for f in result.files if f.warnings)

    warn_stat = ""
    if files_with_warnings:
        warn_stat += f"""
  <div class="stat-div"></div>
  <div class="stat warn"><span class="num">{files_with_warnings}</span><span class="lbl">Warnings</span></div>"""
    if files_absent:
        warn_stat += f"""
  <div class="stat-div"></div>
  <div class="stat warn"><span class="num">{files_absent}</span><span class="lbl">Absent Files</span></div>"""
    if render_errors_count:
        warn_stat += f"""
  <div class="stat-div"></div>
  <div class="stat err"><span class="num">{render_errors_count}</span><span class="lbl">Errors</span></div>"""

    # Part navigation bar + per-part sub-stats (injected when paginated)
    part_nav_html   = ""
    part_stats_html = ""
    if pagination:
        cur   = pagination["current"]
        total = pagination["total"]
        _nav_link_items = []
        for p in pagination["parts"]:
            _is_active = p["url"] == "#"
            _pdiffs  = p.get("diffs", 0)
            _pabsent = p.get("absent", 0)
            if _pdiffs > 0 and _pabsent > 0:
                _badge = f'<span style="color:#bf360c;font-size:10px;font-weight:700">&#9888;{_pdiffs}d+{_pabsent}a</span>'
            elif _pdiffs > 0:
                _badge = f'<span style="color:#c62828;font-size:10px;font-weight:700">&#9888;{_pdiffs}&nbsp;diff{"s" if _pdiffs!=1 else ""}</span>'
            elif _pabsent > 0:
                _badge = f'<span style="color:#e65100;font-size:10px;font-weight:700">&#9888;&nbsp;absent</span>'
            else:
                _badge = '<span style="color:#388e3c;font-size:10px">&#10003;&nbsp;OK</span>'
            _nav_link_items.append(
                f'<a href="{p["url"]}" class="part-nav-link{"active" if _is_active else ""}">'
                f'{p["label"]}</a>&nbsp;{_badge}'
            )
        links = " &nbsp;|&nbsp; ".join(_nav_link_items)
        part_nav_html = (
            f'<div class="part-nav-bar">'
            f'<a href="audit_report.html" class="part-nav-link" '
            f'   style="background:#0d47a1;padding:2px 10px;border-radius:3px;'
            f'          color:#fff;text-decoration:none;margin-right:8px">'
            f'&#8592; Main Index</a>'
            f'<span class="part-nav-label">Part {cur} of {total}:</span> {links}'
            f'</div>'
        )
        if files_js is not None:
            part_files   = len(files_js)
            part_diffs   = sum(1 for f in files_js if f.get("mismatchCount", 0) > 0)
            part_absent  = sum(1 for f in files_js if (f.get("absentCount") or 0) > 0)
            part_mm      = sum(f.get("mismatchCount", 0) for f in files_js)
            _part_absent_note = f' &nbsp;|&nbsp; <strong style="color:#e65100">{part_absent}</strong> absent' if part_absent else ''
            part_stats_html = (
                f'<div class="summary-sub">'
                f'<span><span class="lbl">This part:</span>'
                f' {part_files} files &nbsp;|&nbsp;'
                f' <strong style="color:#c62828">{part_diffs}</strong> with diffs'
                f'{_part_absent_note} &nbsp;|&nbsp;'
                f' {part_mm} mismatches</span>'
                f'<span style="margin-left:auto;color:#bbb">Full run: {total_files} files, '
                f'{files_differ} with diffs, {files_absent} absent, {total_mm} mismatches</span>'
                f'</div>'
            )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Config Audit Report &mdash; {ts_display}</title>
<style>{_CSS}
.part-nav-bar{{background:#1a3a6a;padding:5px 22px;font-size:12px;
              display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.part-nav-label{{color:#9ab;font-weight:600}}
.part-nav-link{{color:#9ab;text-decoration:none}}
.part-nav-link:hover,.part-nav-link.active{{color:#fff}}
</style>
</head>
<body>
{part_nav_html}

<div class="page-header">
  <div class="header-title">
    <h1>Config Audit Report</h1>
    <div class="meta">
      <span><label>Nodes:</label>{node_list}</span>
      <span><label>Generated:</label>{ts_display}</span>
      <span><label>Files:</label>{total_files} compared, {files_differ} with differences</span>
    </div>
  </div>
  <div class="header-actions">
    <span id="save-status-msg" style="display:none;font-size:11px;color:#a5d6a7;
          padding:4px 10px;background:#1b5e20;border-radius:4px;white-space:nowrap"></span>
    <a class="hdr-btn" href="audit_diffs.xlsx" download title="Download formatted XLSX report of files with differences">&#8659; Export Diffs XLSX</a>
    <button class="hdr-btn" onclick="openChangeLog()">
      &#9998; Change Log <span id="change-count" class="change-counter">0</span>
    </button>
    <button class="hdr-btn accent" onclick="saveAllChanges()" title="Save all changed configs to output directory">&#128190; Save All</button>
    <button class="hdr-btn accent" onclick="exportPatch()">&#8659; Export Patch</button>
    <button class="hdr-btn" onclick="exportChangeLogText()">&#8659; Export Log</button>
  </div>
</div>

<div class="summary">
  <div class="summary-row">
    <div class="stat"><span class="num">{total_files}</span><span class="lbl">Files</span></div>
    <div class="stat-div"></div>
    <div class="stat err"><span class="num">{files_differ}</span><span class="lbl">With Diffs</span></div>
    <div class="stat-div"></div>
    <div class="stat"><span class="num">{total_mm}</span><span class="lbl">Mismatches</span></div>
    <div class="stat-div"></div>
    <div class="stat"><span class="num">{binary_diff}</span><span class="lbl">Binary Diff</span></div>{warn_stat}
  </div>
</div>
{part_stats_html}

<!-- Tab navigation -->
<div class="tab-bar">
  <button class="tab-btn active" data-tab="files" onclick="switchTab('files')">
    &#128196; Config Files
  </button>
  <button class="tab-btn" data-tab="skipped" onclick="switchTab('skipped')">
    &#9888; Skipped Backups <span id="tab-count-skipped" class="tab-count">0</span>
  </button>
  <button class="tab-btn" data-tab="filtered" onclick="switchTab('filtered')">
    &#128683; Filtered Files <span id="tab-count-filtered" class="tab-count">0</span>
  </button>
</div>

<!-- Tab: Config Files (default) -->
<div id="tab-files" class="tab-panel active">
<div class="layout">
  <div class="sidebar">
    <div class="sidebar-title">
      <span class="sidebar-title-text">Files</span>
      <button id="sidebar-diffs-toggle" class="diffs-only-toggle"
              onclick="toggleSidebarDiffsOnly()" title="Show only files with differences">
        Diffs only
      </button>
    </div>
    <div class="sidebar-search">
      <div style="position:relative">
        <input type="text" id="sidebar-search-input" placeholder="Search files\u2026 (Ctrl+K)"
               oninput="filterFiles(this.value)"
               onkeydown="if(event.key==='Enter'){{event.preventDefault();_searchFirstVisible();}}
                          else if(event.key==='Escape'){{clearFileSearch();}}">
        <button onclick="clearFileSearch()" title="Clear search"
                style="position:absolute;right:4px;top:50%;transform:translateY(-50%);
                       background:none;border:none;cursor:pointer;color:#aaa;font-size:14px;
                       line-height:1;padding:0 2px">&#10005;</button>
      </div>
      <div style="margin-top:3px;min-height:14px">
        <span id="search-match-badge"
              style="display:none;font-size:10px;color:#fff;border-radius:8px;
                     padding:1px 7px;font-weight:600"></span>
      </div>
    </div>
    <!-- Diff quick-list at top of sidebar -->
    <div class="diff-quicklist" id="diff-quicklist">
      <div class="diff-quicklist-hdr" onclick="toggleDiffQuickList(this)">
        <span class="dir-chev">&#9660;</span>
        <span style="flex:1">Files with differences</span>
      </div>
      <div class="diff-quicklist-body"></div>
    </div>
    <div class="sidebar-files" id="sidebar-tree"></div>
  </div>
  <div class="main" id="main-panel">
    <!-- Skipped files panel (legacy inline — kept for backward compat; primary view is now the tab) -->
    <div class="skipped-panel" id="skipped-panel" style="display:none">
      <div class="skipped-panel-hdr" onclick="toggleSkippedPanel()">
        <span id="skipped-chev">&#9654;</span>
        &#8680; Skipped Files &nbsp;<span class="skipped-count" style="font-weight:400;color:#888"></span>
      </div>
      <div class="skipped-panel-body" id="skipped-panel-body" style="display:none"></div>
    </div>
    <!-- Report errors panel -->
    <div class="errors-panel" id="errors-panel">
      <div class="errors-panel-hdr" onclick="toggleErrorsPanel()">
        <span id="errors-chev">&#9654;</span>
        &#9888; Processing Errors &nbsp;<span class="errors-count" style="font-weight:400"></span>
      </div>
      <div id="errors-panel-body" style="display:none">
        <table class="errors-table">
          <thead><tr><th>File</th><th>Error</th><th>Present in</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
    <div class="empty-panel" id="empty-panel">Select a file from the sidebar to begin.</div>
  </div>
</div><!-- end .layout -->
</div><!-- end #tab-files -->

<!-- Tab: Skipped Backups -->
<div id="tab-skipped" class="tab-panel">
  <div class="tab-fullpage">
    <div class="tab-fullpage-hdr">
      <button class="tab-back-btn" onclick="switchTab('files')">&#8592; Back to Config Files</button>
      <span class="tab-fullpage-title">&#9888; Skipped Backup Files</span>
    </div>
    <p style="font-size:12px;color:#666;margin-bottom:12px">
      Files below were auto-detected as backups and skipped during comparison.
      Click <strong>Copy no_skip rule</strong> to generate a configuration entry
      that will force inclusion in future runs.
    </p>
    <div class="tab-section-hdr">Backup files detected</div>
    <div id="skipped-tab-body"></div>
  </div>
</div>

<!-- Tab: Filtered Files -->
<div id="tab-filtered" class="tab-panel">
  <div class="tab-fullpage">
    <div class="tab-fullpage-hdr">
      <button class="tab-back-btn" onclick="switchTab('files')">&#8592; Back to Config Files</button>
      <span class="tab-fullpage-title">&#128683; Files Excluded by Filter</span>
    </div>
    <p style="font-size:12px;color:#666;margin-bottom:12px">
      Files below matched an exclusion rule in the filter file and were not compared.
      Click <strong>Copy include rule</strong> to generate a configuration entry
      that will force inclusion in future runs.
    </p>
    <div class="tab-section-hdr">Filter-excluded files</div>
    <div id="filtered-tab-body"></div>
  </div>
</div>

<!-- Change Log Modal -->
<div class="modal-overlay" id="cl-modal" onclick="if(event.target===this)closeChangeLog()">
  <div class="modal">
    <div class="modal-hdr">
      <h2>&#9998; Change Log</h2>
      <button class="modal-close" onclick="closeChangeLog()">&#10005;</button>
    </div>
    <div class="modal-toolbar">
      <span style="font-size:12px;color:#ccc">All pending corrections made in this session</span>
    </div>
    <div class="modal-body" id="cl-modal-body"></div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeChangeLog()">Close</button>
      <button class="btn-primary"   onclick="exportChangeLogText()">&#8659; Export Log (.txt)</button>
      <button class="btn-primary"   onclick="exportPatch()">&#8659; Export Patch (.json)</button>
    </div>
  </div>
</div>

<!-- Nav Guard Modal -->
<div class="modal-overlay" id="navguard-modal">
  <div class="modal modal-sm">
    <div class="modal-hdr">
      <h2>&#9888; Unsaved Changes</h2>
    </div>
    <div class="modal-body">
      <p id="navguard-msg"></p>
      <p id="navguard-sub" style="font-size:11px;color:#666"></p>
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="navGuardCancel()">Cancel</button>
      <button class="btn-secondary" onclick="navGuardContinue()">Continue Without Saving</button>
      <button id="navguard-save-btn" class="btn-default" onclick="navGuardSaveAndContinue()">Save &amp; Continue</button>
    </div>
  </div>
</div>

<!-- Output Dir Prompt Modal -->
<div class="modal-overlay" id="od-modal" onkeydown="if(event.key==='Enter')outputDirConfirm()">
  <div class="modal modal-sm">
    <div class="modal-hdr">
      <h2>&#128190; Set Output Directory</h2>
    </div>
    <div class="modal-body">
      <p>No output directory is configured. Enter the local path where corrected config files should be saved.</p>
      <p style="font-size:11px;color:#666">Files will be written as: <code>&lt;output_dir&gt;/&lt;Node&gt;/&lt;rel/path&gt;</code></p>
      <input type="text" id="od-input" placeholder="e.g. /home/user/corrections" />
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="outputDirCancel()">Cancel</button>
      <button class="btn-default" onclick="outputDirConfirm()">Confirm &amp; Save</button>
    </div>
  </div>
</div>

<div class="legend-bar">
  <span class="lbl">Legend</span>
  <div class="leg-item"><div class="leg-swatch" style="background:#fffde7;border:1px solid #f9a825"></div> Value mismatch</div>
  <div class="leg-item"><div class="leg-swatch" style="background:#e3f2fd;border:1px solid #1565c0"></div> Pending change</div>
  <div class="leg-item"><div class="leg-swatch" style="background:repeating-linear-gradient(45deg,#fff,#fff 4px,#fff8e1 4px,#fff8e1 8px);border:1px solid #e0e0e0"></div> Key missing</div>
  <div class="leg-item"><div class="leg-swatch" style="background:repeating-linear-gradient(45deg,#f5f5f5,#f5f5f5 4px,#eee 4px,#eee 8px);border:1px solid #e0e0e0"></div> File absent</div>
  <div class="leg-item"><div class="leg-swatch" style="background:#fff;border:1px solid #ccc"></div> Values match</div>
  <div style="margin-left:auto;font-size:10px;color:#aaa">
    To apply changes: Export Patch &rarr; <code>python3 ConfigMergeTool.py --apply-audit-patch &lt;patch.json&gt; --output-dir &lt;dir&gt;</code>
  </div>
</div>

<script>
const AUDIT_DATA = {_DATA_SLOT};
</script>
<script>
{_JS}
</script>
</body>
</html>"""
    head, tail = page.split(_DATA_SLOT)
    return head, data_js, tail


def _build_html(result: "AuditResult", files_js=None, pagination=None) -> str:
    """Build a self-contained audit report HTML string (see _render_html_parts)."""
    return "".join(_render_html_parts(result, files_js=files_js, pagination=pagination))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pagination helpers (Phase 3.1)
# ---------------------------------------------------------------------------

_PART_SIZE_LIMIT = 22 * 1024 * 1024   # 22 MB per part (keeps under 25 MB with CSS/JS)


def _split_into_parts(result: "AuditResult"):
    """Serialise files and split into size-bounded chunks.

    Returns a list of file-list chunks.  Each chunk is a list of the
    serialised file dicts that fit within _PART_SIZE_LIMIT.
    """
    # Serialise all files individually
    all_data = _serialise_result(result)
    files_js  = all_data["files"]

    if not files_js:
        return [files_js]

    # Estimate total JSON size
    total_est = sum(len(json.dumps(f, ensure_ascii=False)) for f in files_js)
    if total_est <= _PART_SIZE_LIMIT:
        return [files_js]   # single part — no split needed

    # Split greedily
    parts: list = []
    current_chunk: list = []
    current_size = 0

    for fjs in files_js:
        fsize = len(json.dumps(fjs, ensure_ascii=False))
        if current_chunk and current_size + fsize > _PART_SIZE_LIMIT:
            parts.append(current_chunk)
            current_chunk = []
            current_size  = 0
        current_chunk.append(fjs)
        current_size += fsize

    if current_chunk:
        parts.append(current_chunk)

    return parts


def _build_index_html(result: "AuditResult", parts_meta: list) -> str:
    """Build an interactive index page with directory tree, diff filter, and skipped files."""
    ts_display = (
        result.run_timestamp[:4]    + "-" +
        result.run_timestamp[4:6]   + "-" +
        result.run_timestamp[6:8]   + " " +
        result.run_timestamp[9:11]  + ":" +
        result.run_timestamp[11:13] + ":" +
        result.run_timestamp[13:15]
    )

    total_files   = len(result.files)
    files_differ  = sum(1 for f in result.files if f.mismatch_count > 0)
    files_absent  = sum(1 for f in result.files if f.absent_count > 0)
    files_issues  = sum(1 for f in result.files if f.mismatch_count > 0 or f.absent_count > 0)
    total_mm      = result.total_mismatches
    node_list    = ", ".join(result.nodes)
    num_parts    = len(parts_meta)

    # Part links with diff/absent badge indicators
    part_link_items = []
    for p in parts_meta:
        part_diffs  = sum(1 for f in p["files"] if f.get("mismatchCount", 0) > 0)
        part_absent = sum(1 for f in p["files"] if (f.get("absentCount") or 0) > 0)
        if part_diffs > 0 and part_absent > 0:
            badge = f'<span style="color:#bf360c;font-size:10px;font-weight:700">&#9888;{part_diffs}d+{part_absent}a</span>'
        elif part_diffs > 0:
            badge = f'<span style="color:#c62828;font-size:10px;font-weight:700">&#9888;{part_diffs}&nbsp;diff{"s" if part_diffs!=1 else ""}</span>'
        elif part_absent > 0:
            badge = f'<span style="color:#e65100;font-size:10px;font-weight:700">&#9888;&nbsp;absent</span>'
        else:
            badge = '<span style="color:#388e3c;font-size:10px">&#10003;&nbsp;OK</span>'
        part_link_items.append(f'<a href="{p["url"]}">{p["label"]}</a>&nbsp;{badge}')
    part_links = " &nbsp;|&nbsp; ".join(part_link_items)

    # Build path→(part_url, mc, ldc, ft, present) lookup
    file_info: dict = {}
    for part in parts_meta:
        for fjs in part["files"]:
            path = fjs.get("path", "")
            mc   = fjs.get("mismatchCount", 0)
            ldc  = fjs.get("logicalDiffCount", 0)
            ft   = fjs.get("type", "")
            abs_in = [n for n in result.nodes if n not in fjs.get("presentIn", result.nodes)]
            link = f'{part["url"]}#{_url_quote(path, safe="")}'
            file_info[path] = {"mc": mc, "ldc": ldc, "ft": ft, "link": link,
                               "present": fjs.get("presentIn", []), "absent": abs_in}

    # Build tree structure in Python
    tree: dict = {}  # path -> {dirs: set, files: list}

    def _ensure_dir(d: str) -> None:
        if d not in tree:
            tree[d] = {"dirs": [], "files": [], "diffCount": 0, "totalCount": 0, "absentCount": 0}

    for path in sorted(file_info.keys()):
        segs = path.split("/")
        for depth in range(len(segs) - 1):
            parent = "/".join(segs[:depth]) if depth else ""
            child  = "/".join(segs[:depth + 1])
            _ensure_dir(parent)
            _ensure_dir(child)
            if child not in tree[parent]["dirs"]:
                tree[parent]["dirs"].append(child)
        parent = "/".join(segs[:-1]) if len(segs) > 1 else ""
        _ensure_dir(parent)
        info = file_info[path]
        tree[parent]["files"].append(path)
        tree[parent]["totalCount"] += 1
        if info["mc"] > 0: tree[parent]["diffCount"] += 1
        if info["absent"]: tree[parent]["absentCount"] += 1

    # Bubble counts up
    def _bubble(d: str) -> None:
        for sub in tree.get(d, {}).get("dirs", []):
            _bubble(sub)
            tree[d]["diffCount"]   += tree[sub]["diffCount"]
            tree[d]["totalCount"]  += tree[sub]["totalCount"]
            tree[d]["absentCount"] += tree[sub]["absentCount"]

    _bubble("")

    def _render_dir(d: str, depth: int) -> str:
        node = tree.get(d, {"dirs": [], "files": [], "diffCount": 0, "totalCount": 0, "absentCount": 0})
        diffs = node["diffCount"]
        label = d.split("/")[-1] + "/" if d else "(root)"
        indent_px = depth * 16
        auto_open = diffs > 0 or node["absentCount"] > 0
        chev = "▼" if auto_open else "▶"
        body_display = "block" if auto_open else "none"

        if diffs > 0 and node["absentCount"] > 0:
            dir_badge = (f'<span class="dir-diff-badge">{diffs} diff{"s" if diffs!=1 else ""}</span>'
                         f'<span class="dir-warn-badge">⚠ absent</span>')
        elif diffs > 0:
            dir_badge = f'<span class="dir-diff-badge">{diffs} diff{"s" if diffs!=1 else ""}</span>'
        elif node["absentCount"] > 0:
            dir_badge = '<span class="dir-warn-badge">⚠ absent</span>'
        else:
            dir_badge = '<span class="dir-ok-badge">✓</span>'

        file_rows = ""
        for fp in node["files"]:
            info = file_info[fp]
            fname = fp.split("/")[-1]
            mc, ldc, ft, link = info["mc"], info["ldc"], info["ft"], info["link"]
            absent_nodes = info["absent"]
            # Build badge: show diff badge + absent badge independently
            badge_parts = []
            if mc > 0:
                badge_parts.append(f'<span class="idx-diff-badge">{mc} diff{"s" if mc!=1 else ""}</span>')
            if absent_nodes:
                badge_parts.append('<span class="idx-absent-badge">⚠ absent</span>')
            if not badge_parts:
                if ldc > 0:
                    badge_parts.append(f'<span class="idx-logical-badge">~{ldc} logical</span>')
                else:
                    badge_parts.append('<span class="idx-ok-badge">✓</span>')
            badge = "".join(badge_parts)

            if mc > 0 and absent_nodes:
                row_cls = "idx-row idx-row-diff idx-row-absent"
            elif mc > 0:
                row_cls = "idx-row idx-row-diff"
            elif absent_nodes:
                row_cls = "idx-row idx-row-absent"
            else:
                row_cls = "idx-row idx-row-ok"

            absent_info = ""
            if absent_nodes:
                absent_info = f'<span class="idx-absent-nodes">absent in: {", ".join(absent_nodes)}</span>'

            _has_issue = 1 if (mc > 0 or absent_nodes) else 0
            file_rows += (
                f'<tr class="{row_cls}" data-diff="{_has_issue}">'
                f'<td style="padding-left:{indent_px+32}px">'
                f'  <a href="{link}" class="idx-file-link">{fname}</a>'
                f'  {absent_info}'
                f'</td>'
                f'<td><span class="idx-type">{ft}</span></td>'
                f'<td>{badge}</td>'
                f'</tr>\n'
            )

        sub_html = "".join(_render_dir(sub, depth + 1) for sub in node["dirs"])

        _dir_has_issue = 1 if (diffs > 0 or node["absentCount"] > 0) else 0
        return (
            f'<tr class="idx-dir-row" data-diff="{_dir_has_issue}">'
            f'<td colspan="3" style="padding:0">'
            f'  <div class="idx-dir-hdr" style="padding-left:{indent_px+8}px"'
            f'       onclick="toggleIdxDir(this)">'
            f'    <span class="idx-chev">{chev}</span>'
            f'    <span class="idx-dir-name">{label}</span>'
            f'    {dir_badge}'
            f'  </div>'
            f'  <div class="idx-dir-body" style="display:{body_display}">'
            f'    <table style="width:100%;border-collapse:collapse">'
            f'      {sub_html}{file_rows}'
            f'    </table>'
            f'  </div>'
            f'</td></tr>\n'
        )

    tree_html = _render_dir("", 0)

    # Diff-files quick-list: files with content diffs OR absent from some nodes
    diff_file_list = sorted(
        [(path, info) for path, info in file_info.items()
         if info["mc"] > 0 or info["absent"]],
        key=lambda x: (-x[1]["mc"], bool(x[1]["absent"])),
    )
    files_with_issues = len(diff_file_list)
    if diff_file_list:
        _ql_rows = ""
        for _dp, _di in diff_file_list:
            _part_url = _di["link"].split("#")[0]
            _part_lbl = next((m["label"] for m in parts_meta if m["url"] == _part_url), _part_url)
            _mc     = _di["mc"]
            _ft     = _di["ft"]
            _absent = ", ".join(_di["absent"]) if _di["absent"] else ""
            # Status column: show diff badge, absent badge, or both
            _status_parts = []
            if _mc > 0:
                _status_parts.append(f'<span class="idx-diff-badge">{_mc} diff{"s" if _mc!=1 else ""}</span>')
            if _absent:
                _status_parts.append(f'<span class="idx-absent-badge">&#9888; absent</span>')
            _status_td  = f'<td>{"".join(_status_parts)}</td>'
            _absent_td  = f'<td style="color:#e65100;font-size:11px">{_absent}</td>' if _absent else "<td></td>"
            _ql_rows += (
                f'<tr>'
                f'<td><a href="{_di["link"]}" class="idx-file-link">{_dp}</a></td>'
                f'<td><span class="idx-type">{_ft}</span></td>'
                f'{_status_td}'
                f'{_absent_td}'
                f'<td><a href="{_di["link"]}" class="diff-ql-part-link">{_part_lbl} &rarr;</a></td>'
                f'</tr>\n'
            )
        diff_ql_html = f"""<div class="diff-ql" id="diff-ql">
  <div class="diff-ql-hdr" onclick="toggleDiffQl()">
    <span class="diff-ql-chev" id="diff-ql-chev">&#9660;</span>
    &#9888;&nbsp; {files_with_issues} file{"s" if files_with_issues!=1 else ""} with differences or absent nodes &mdash; click to expand / collapse
  </div>
  <div id="diff-ql-body" class="diff-ql-body">
    <table class="diff-ql-table">
      <thead><tr><th>File</th><th>Type</th><th>Status</th><th>Absent in</th><th>Part</th></tr></thead>
      <tbody>{_ql_rows}</tbody>
    </table>
  </div>
</div>"""
    else:
        diff_ql_html = ""

    # Skipped files section — build rows for the tab panels
    n_skipped  = len(result.skipped_backups)
    n_filtered = len(result.filtered_files)

    def _skipped_table(entries: list, rule_type: str) -> str:
        if not entries:
            return '<p style="padding:12px;color:#999;font-size:12px">None.</p>'
        head = '<table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff"><thead><tr style="background:#f0f2f6"><th style="padding:6px 12px;text-align:left">Path</th><th style="padding:6px 12px;text-align:left">Reason</th><th style="padding:6px 12px;text-align:left">Base Dir</th></tr></thead><tbody>'
        body = ""
        for e in entries:
            body += f'<tr><td style="font-family:monospace;padding:5px 12px;border-bottom:1px solid #f0f2f6">{e.get("rel_path","")}</td><td style="padding:5px 12px;border-bottom:1px solid #f0f2f6;color:#666">{e.get("reason","")}</td><td style="padding:5px 12px;border-bottom:1px solid #f0f2f6;color:#888;font-size:11px">{e.get("base_dir","")}</td></tr>\n'
        return head + body + "</tbody></table>"

    skipped_tab_content  = _skipped_table(result.skipped_backups, "backup")
    filtered_tab_content = _skipped_table(result.filtered_files, "filter")


    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Config Audit Report &mdash; Index &mdash; {ts_display}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;background:#f4f6f9;color:#222}}
.sticky-top{{position:sticky;top:0;z-index:100;background:#fff;
             box-shadow:0 2px 6px rgba(0,0,0,.08)}}
.hdr{{background:#1e2a3a;color:#fff;padding:12px 24px;display:flex;align-items:center;gap:12px}}
.hdr-title{{flex:1}}
.hdr h1{{font-size:17px;margin-bottom:3px}}
.hdr .meta{{font-size:11px;color:#9ab}}
.hdr-actions{{display:flex;gap:6px;flex-shrink:0}}
.hdr-btn{{background:#2e3d52;color:#cde;border:1px solid #3d5068;border-radius:4px;
          padding:5px 10px;font-size:11px;cursor:pointer;white-space:nowrap}}
.hdr-btn:hover{{background:#3d5068}}
.stats{{background:#fff;padding:10px 24px;border-bottom:1px solid #dde3ed;
        display:flex;gap:20px;flex-wrap:wrap;align-items:center}}
.stat{{display:flex;flex-direction:column;align-items:center;min-width:60px}}
.stat .num{{font-size:18px;font-weight:700;color:#1e2a3a}}
.stat .lbl{{font-size:10px;color:#777;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}}
.stat.err .num{{color:#c62828}}
.stat.warn .num{{color:#e65100}}
.parts-bar{{background:#e8f0fe;padding:7px 24px;border-bottom:1px solid #c0cfe8;
            font-size:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.parts-bar a{{color:#1565c0;margin-right:4px}}
/* Tab bar */
.idx-tab-bar{{display:flex;background:#fff;border-bottom:2px solid #dde3ed}}
.idx-tab-btn{{padding:7px 18px;font-size:12px;font-weight:600;color:#666;border:none;
              background:none;cursor:pointer;border-bottom:3px solid transparent;
              margin-bottom:-2px;white-space:nowrap}}
.idx-tab-btn:hover{{color:#1e2a3a;background:#f4f6f9}}
.idx-tab-btn.active{{color:#1565c0;border-bottom-color:#1565c0;background:#fff}}
.idx-tab-count{{background:#e0e6f0;color:#555;border-radius:9px;padding:1px 7px;
                font-size:10px;margin-left:5px;font-weight:400}}
.idx-tab-count.has{{background:#c62828;color:#fff}}
.idx-tab-panel{{display:none}}
.idx-tab-panel.active{{display:block}}
/* Filter bar */
.filter-bar{{padding:8px 24px;border-bottom:1px solid #dde3ed;background:#fff;
             display:flex;align-items:center;gap:12px;font-size:12px}}
.filter-toggle{{background:none;border:1px solid #c0c8d8;border-radius:10px;
                padding:3px 10px;font-size:11px;cursor:pointer;color:#555}}
.filter-toggle.active{{background:#c62828;color:#fff;border-color:#c62828}}
.content{{padding:16px 24px 40px}}
.tree-table{{width:100%;border-collapse:collapse;background:#fff;
             border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
/* Dir rows */
.idx-dir-hdr{{display:flex;align-items:center;gap:6px;padding:7px 10px;
              cursor:pointer;font-weight:700;font-size:12px;color:#1e2a3a;
              background:#f8fafc;border-bottom:1px solid #eef0f4;user-select:none}}
.idx-dir-hdr:hover{{background:#eef2f8}}
.idx-chev{{font-size:10px;color:#999;width:14px;flex-shrink:0}}
.idx-dir-name{{flex:1}}
.dir-diff-badge{{background:#c62828;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
.dir-ok-badge{{background:#388e3c;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
.dir-warn-badge{{background:#e65100;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
/* File rows */
.idx-row td{{padding:5px 12px;border-bottom:1px solid #eef0f4;font-size:12px}}
.idx-row:hover td{{background:#f5f8ff}}
.idx-row-diff td{{background:#fffde7}}
.idx-row-diff:hover td{{background:#fff9c4}}
.idx-row-absent td{{background:#fff8e1}}
.idx-row-ok{{opacity:.7}}
.idx-file-link{{color:#1565c0;text-decoration:none;font-family:monospace}}
.idx-file-link:hover{{text-decoration:underline}}
.idx-absent-nodes{{font-size:10px;color:#e65100;margin-left:8px}}
.idx-type{{font-size:10px;color:#888;background:#f0f2f6;padding:1px 6px;border-radius:3px}}
.idx-diff-badge{{background:#c62828;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
.idx-ok-badge{{background:#388e3c;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
.idx-logical-badge{{background:#7b1fa2;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
.idx-absent-badge{{background:#e65100;color:#fff;font-size:10px;border-radius:6px;padding:1px 6px}}
/* Diff-files quick-list */
.diff-ql{{margin:0 0 0 0;border-bottom:2px solid #ffcdd2;background:#fff}}
.diff-ql-hdr{{display:flex;align-items:center;gap:8px;padding:8px 24px;
              background:#ffebee;cursor:pointer;font-size:12px;font-weight:700;
              color:#c62828;user-select:none;border-bottom:1px solid #ffcdd2;
              position:sticky;top:0;z-index:50}}
.diff-ql-hdr:hover{{background:#ffcdd2}}
.diff-ql-chev{{font-size:10px;width:14px;flex-shrink:0}}
.diff-ql-body{{padding:0 24px 10px}}
.diff-ql-table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}}
.diff-ql-table th{{background:#f0f2f6;padding:5px 10px;font-size:11px;font-weight:600;
                   color:#444;text-align:left;border-bottom:1px solid #dde3ed}}
.diff-ql-table td{{padding:5px 10px;border-bottom:1px solid #f0f2f6}}
.diff-ql-table tr:hover td{{background:#fff8f8}}
.diff-ql-part-link{{color:#1565c0;font-size:11px;white-space:nowrap}}
/* Skipped-tab content */
.skipped-content{{padding:16px 24px 40px}}
.back-lnk{{display:inline-block;background:#f0f2f6;border:1px solid #c0c8d8;border-radius:4px;
           padding:4px 12px;font-size:11px;cursor:pointer;color:#1e2a3a;
           text-decoration:none;margin-bottom:14px}}
.back-lnk:hover{{background:#dde3ed}}
</style>
</head>
<body>
<div class="sticky-top">
  <div class="hdr">
    <div class="hdr-title">
      <h1>Config Audit Report &mdash; Index</h1>
      <div class="meta">Generated: {ts_display} &nbsp;|&nbsp; Nodes: {node_list}</div>
    </div>
    <div class="hdr-actions">
      <a class="hdr-btn" href="audit_diffs.xlsx" download title="Download formatted XLSX report of files with differences">&#8659; Export Diffs XLSX</a>
    </div>
  </div>
  <div class="stats">
    <div class="stat"><span class="num">{total_files}</span><span class="lbl">Files</span></div>
    <div class="stat err"><span class="num">{files_differ}</span><span class="lbl">With Diffs</span></div>
    <div class="stat"><span class="num">{total_mm}</span><span class="lbl">Mismatches</span></div>
    <div class="stat warn"><span class="num">{files_absent}</span><span class="lbl">Absent</span></div>
    <div class="stat"><span class="num">{num_parts}</span><span class="lbl">Parts</span></div>
  </div>
  <div class="parts-bar">
    <strong>Jump to part:</strong> {part_links}
  </div>
  <div class="idx-tab-bar">
    <button class="idx-tab-btn active" data-itab="files" onclick="switchIdxTab('files')">
      &#128196; Config Files
    </button>
    <button class="idx-tab-btn" data-itab="skipped" onclick="switchIdxTab('skipped')">
      &#9888; Skipped Backups
      <span class="idx-tab-count{' has' if n_skipped else ''}" id="itab-cnt-skipped">{n_skipped}</span>
    </button>
    <button class="idx-tab-btn" data-itab="filtered" onclick="switchIdxTab('filtered')">
      &#128683; Filtered Files
      <span class="idx-tab-count{' has' if n_filtered else ''}" id="itab-cnt-filtered">{n_filtered}</span>
    </button>
  </div>
</div>

<!-- Tab: Config Files -->
<div id="itab-files" class="idx-tab-panel active">
<div class="filter-bar">
  <button id="idx-diffs-toggle" class="filter-toggle" onclick="toggleIdxDiffsOnly()">
    Show diffs only
  </button>
  <span style="color:#aaa;font-size:11px">Click a file to open the detail report. Click a directory header to collapse/expand.</span>
</div>

{diff_ql_html}

<div class="content">
  <table class="tree-table">
    <thead style="position:sticky;top:0;z-index:10">
      <tr style="background:#1e2a3a;color:#fff">
        <th style="padding:8px 12px;text-align:left;font-size:12px">File / Directory</th>
        <th style="padding:8px 12px;text-align:left;font-size:12px;width:80px">Type</th>
        <th style="padding:8px 12px;text-align:left;font-size:12px;width:140px">Status</th>
      </tr>
    </thead>
    <tbody id="idx-tree-body">
{tree_html}
    </tbody>
  </table>
</div>
</div><!-- end itab-files -->

<!-- Tab: Skipped Backups -->
<div id="itab-skipped" class="idx-tab-panel">
  <div class="skipped-content">
    <a class="back-lnk" onclick="switchIdxTab('files')">&#8592; Back to Config Files</a>
    <h2 style="font-size:14px;color:#1e2a3a;margin-bottom:8px">&#9888; Skipped Backup Files ({n_skipped})</h2>
    <p style="font-size:12px;color:#666;margin-bottom:12px">These files were auto-detected as backups and skipped.</p>
    {skipped_tab_content}
  </div>
</div>

<!-- Tab: Filtered Files -->
<div id="itab-filtered" class="idx-tab-panel">
  <div class="skipped-content">
    <a class="back-lnk" onclick="switchIdxTab('files')">&#8592; Back to Config Files</a>
    <h2 style="font-size:14px;color:#1e2a3a;margin-bottom:8px">&#128683; Files Excluded by Filter ({n_filtered})</h2>
    <p style="font-size:12px;color:#666;margin-bottom:12px">These files matched an exclusion rule and were not compared.</p>
    {filtered_tab_content}
  </div>
</div>

<script>
function switchIdxTab(tabName) {{
  document.querySelectorAll('.idx-tab-btn').forEach(b => {{
    b.classList.toggle('active', b.dataset.itab === tabName);
  }});
  document.querySelectorAll('.idx-tab-panel').forEach(p => {{
    p.classList.toggle('active', p.id === 'itab-' + tabName);
  }});
}}

function toggleDiffQl() {{
  let body = document.getElementById('diff-ql-body');
  let chev = document.getElementById('diff-ql-chev');
  if (!body) return;
  let open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (chev) chev.innerHTML = open ? '&#9654;' : '&#9660;';
}}

function toggleIdxDir(hdr) {{
  let body = hdr.nextElementSibling;
  let chev = hdr.querySelector('.idx-chev');
  let open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (chev) chev.textContent = open ? '▶' : '▼';
}}

let idxDiffsOnly = false;
function toggleIdxDiffsOnly() {{
  idxDiffsOnly = !idxDiffsOnly;
  let btn = document.getElementById('idx-diffs-toggle');
  if (btn) btn.classList.toggle('active', idxDiffsOnly);
  // Show/hide matched file rows
  document.querySelectorAll('.idx-row-ok').forEach(r => {{
    r.style.display = idxDiffsOnly ? 'none' : '';
  }});
  // Auto-collapse dirs with no diffs; expand dirs with diffs
  document.querySelectorAll('.idx-dir-row').forEach(row => {{
    let hasDiff = row.dataset.diff === '1';
    row.style.display = (idxDiffsOnly && !hasDiff) ? 'none' : '';
  }});
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTML sanity checker (P3 item 7)
# ---------------------------------------------------------------------------

class _HTMLChecker(_html_parser.HTMLParser):
    """Minimal HTMLParser subclass that records parse errors."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.errors: list = []

    def handle_error(self, message: str) -> None:  # type: ignore[override]
        self.errors.append(message)


def _validate_html(html_str: str, path: str) -> bool:
    """Check generated HTML for common structural problems.

    Prints a warning to stderr if issues are detected.
    Returns True when the check passes, False otherwise.
    """
    return _validate_html_parts(html_str, "", "", path)


def _validate_html_parts(head: str, data_js: str, tail: str, path: str) -> bool:
    """_validate_html for a page kept as head + data_js + tail, without joining it.

    data_js is the AUDIT_DATA JSON inside a <script> element; with no "</script"
    in it (the escaping in _render_html_parts guarantees that) the parser treats
    it as opaque script text, so parsing head + tail gives the same verdict.
    """
    issues: list = []
    pieces = (head, data_js, tail)

    # Structural markers (the pieces meet at "= {" and "};", so none straddles a join)
    if not any("<!DOCTYPE html>" in p for p in pieces):
        issues.append("missing <!DOCTYPE html>")
    if not any("</html>" in p for p in pieces):
        issues.append("missing </html>")
    if not any("</body>" in p for p in pieces):
        issues.append("missing </body>")

    # <script> / </script> balance — unbalanced tags indicate raw-content leakage
    # Use case-insensitive regex so </SCRIPT> variants are also counted.
    open_count  = sum(len(re.findall(r'<script\b', p, re.IGNORECASE)) for p in pieces)
    close_count = sum(len(re.findall(r'</script\b', p, re.IGNORECASE)) for p in pieces)
    if open_count != close_count:
        issues.append(
            f"unbalanced <script> tags "
            f"({open_count} opening, {close_count} closing)"
        )

    # Feed through HTMLParser to catch catastrophic parse failures
    checker = _HTMLChecker()
    try:
        if re.search(r'</script', data_js, re.IGNORECASE):
            checker.feed(head + data_js + tail)
        else:
            checker.feed(head + tail)
        checker.close()
    except Exception as exc:
        issues.append(f"HTMLParser raised: {exc}")
    if checker.errors:
        issues.extend(checker.errors[:3])  # cap at first 3 to avoid log spam

    if issues:
        print(
            f"[CMT-AUD-W009] [WARN ] HTML sanity check FAILED for {path}:\n"
            + "\n".join(f"        • {i}" for i in issues),
            file=sys.stderr,
        )
        return False
    return True


def _write_diffs_xlsx(result: "AuditResult", run_dir: str) -> str:
    """Generate a formatted XLSX report of files with differences or absent nodes.

    Sheets
    ------
    1. Summary      — run metadata and aggregate counts
    2. Issues       — one row per file with diffs or absent nodes (colour-coded)
    3. All Nodes    — per-node present/absent status for every file

    Returns the path to the written .xlsx file.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        # openpyxl not available — skip silently
        return ""

    # ── Palette ───────────────────────────────────────────────────────────
    DARK_FILL    = PatternFill("solid", fgColor="1E2A3A")
    RED_FILL     = PatternFill("solid", fgColor="FFEBEE")
    ORANGE_FILL  = PatternFill("solid", fgColor="FFF3E0")
    BOTH_FILL    = PatternFill("solid", fgColor="FFE0B2")   # diff + absent
    OK_FILL      = PatternFill("solid", fgColor="E8F5E9")
    SECT_FILL    = PatternFill("solid", fgColor="E3F2FD")   # section header
    WHITE_FONT   = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
    HDR_FONT     = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
    BOLD         = Font(bold=True, name="Calibri", size=10)
    NORMAL       = Font(name="Calibri", size=10)
    RED_FONT     = Font(bold=True, color="C62828", name="Calibri", size=10)
    ORANGE_FONT  = Font(bold=True, color="E65100", name="Calibri", size=10)
    GREEN_FONT   = Font(bold=True, color="1B5E20", name="Calibri", size=10)
    WRAP         = Alignment(wrap_text=True, vertical="top")
    TOP          = Alignment(vertical="top")

    def _thin_border():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)

    def _hdr_row(ws, row_num: int, values: list, col_widths: list | None = None) -> None:
        for col, val in enumerate(values, 1):
            c = ws.cell(row=row_num, column=col, value=val)
            c.fill   = DARK_FILL
            c.font   = HDR_FONT
            c.border = _thin_border()
            c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        if col_widths:
            for col, w in enumerate(col_widths, 1):
                ws.column_dimensions[get_column_letter(col)].width = w

    def _set_cell(ws, row: int, col: int, value, font=None, fill=None, align=None) -> None:
        c = ws.cell(row=row, column=col, value=value)
        c.border = _thin_border()
        if font:   c.font      = font
        if fill:   c.fill      = fill
        if align:  c.alignment = align
        else:      c.alignment = TOP

    nodes = result.nodes
    ts    = result.run_timestamp
    ts_display = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"

    files_total   = len(result.files)
    files_differ  = sum(1 for f in result.files if f.mismatch_count > 0)
    files_absent  = sum(1 for f in result.files if f.absent_count  > 0)
    files_ok      = files_total - sum(1 for f in result.files
                                      if f.mismatch_count > 0 or f.absent_count > 0)
    total_mm      = result.total_mismatches

    wb = Workbook()

    # ── Sheet 1: Summary ─────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Summary"
    ws1.column_dimensions["A"].width = 28
    ws1.column_dimensions["B"].width = 60

    def _kv(row, key, val, val_font=None):
        kc = ws1.cell(row=row, column=1, value=key)
        kc.font      = BOLD
        kc.fill      = SECT_FILL
        kc.border    = _thin_border()
        kc.alignment = TOP
        vc = ws1.cell(row=row, column=2, value=val)
        vc.font      = val_font or NORMAL
        vc.border    = _thin_border()
        vc.alignment = WRAP

    r = 1
    ws1.merge_cells(f"A{r}:B{r}")
    title_cell = ws1.cell(row=r, column=1, value="Config Audit Report — Summary")
    title_cell.fill      = DARK_FILL
    title_cell.font      = Font(bold=True, color="FFFFFF", name="Calibri", size=13)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[r].height = 24
    r += 1

    _kv(r, "Report generated",  ts_display);  r += 1
    _kv(r, "Nodes compared",    ", ".join(nodes));  r += 1
    _kv(r, "Node count",        len(nodes));  r += 1
    r += 1  # blank

    ws1.merge_cells(f"A{r}:B{r}")
    sec = ws1.cell(row=r, column=1, value="File Statistics")
    sec.fill = SECT_FILL; sec.font = BOLD; sec.border = _thin_border(); r += 1

    _kv(r, "Total files compared", files_total); r += 1
    _kv(r, "Files matched (no issues)", files_ok,
        Font(bold=True, color="1B5E20", name="Calibri", size=10)); r += 1
    _kv(r, "Files with content diffs", files_differ,
        RED_FONT if files_differ else NORMAL); r += 1
    _kv(r, "Files absent from ≥1 node", files_absent,
        ORANGE_FONT if files_absent else NORMAL); r += 1
    _kv(r, "Total parameter mismatches", total_mm,
        RED_FONT if total_mm else NORMAL); r += 1
    r += 1

    if result.skipped_backups:
        _kv(r, "Backup files skipped", len(result.skipped_backups)); r += 1
    if result.filtered_files:
        _kv(r, "Files excluded by filter", len(result.filtered_files)); r += 1

    ws1.freeze_panes = "A2"

    # ── Sheet 2: Issues ───────────────────────────────────────────────────
    ws2 = wb.create_sheet("Issues")
    issue_files = [f for f in result.files
                   if f.mismatch_count > 0 or f.absent_count > 0]
    issue_files.sort(key=lambda f: (-f.mismatch_count, -f.absent_count, f.rel_path))

    hdrs2 = ["File Path", "Type", "Status", "Mismatches", "Absent From", "Present In",
             "Mismatched Parameters"]
    col_w2 = [55, 8, 18, 11, 30, 30, 60]
    _hdr_row(ws2, 1, hdrs2, col_w2)
    ws2.freeze_panes = "A2"

    for row_i, af in enumerate(issue_files, 2):
        absent_nodes  = [n for n in nodes if n not in af.present_in]
        present_nodes = af.present_in

        if af.mismatch_count > 0 and af.absent_count > 0:
            status    = "Diff + Absent/Missing"
            row_fill  = BOTH_FILL
            stat_font = Font(bold=True, color="BF360C", name="Calibri", size=10)
        elif af.mismatch_count > 0:
            status    = "Diff"
            row_fill  = RED_FILL
            stat_font = RED_FONT
        else:
            status    = "Absent/Missing"
            row_fill  = ORANGE_FILL
            stat_font = ORANGE_FONT

        mm_params = "; ".join(
            p.key or p.compound
            for p in af.params if p.has_mismatch
        )[:500]  # cap at 500 chars to avoid huge cells

        cols = [
            (af.rel_path,                        NORMAL,    None),
            (af.file_type.upper(),               NORMAL,    Alignment(horizontal="center", vertical="top")),
            (status,                             stat_font, None),
            (af.mismatch_count or "",            RED_FONT if af.mismatch_count else NORMAL,
             Alignment(horizontal="center", vertical="top")),
            (", ".join(absent_nodes),            ORANGE_FONT if absent_nodes else NORMAL, WRAP),
            (", ".join(present_nodes),           NORMAL,    WRAP),
            (mm_params,                          NORMAL,    WRAP),
        ]
        ws2.row_dimensions[row_i].height = max(15, 15 * (1 + mm_params.count(";") // 3))
        for col_i, (val, fnt, aln) in enumerate(cols, 1):
            _set_cell(ws2, row_i, col_i, val, font=fnt, fill=row_fill,
                      align=aln or TOP)

    if not issue_files:
        ws2.cell(row=2, column=1, value="No issues found — all files matched on all nodes.").font = GREEN_FONT

    # ── Sheet 3: Node Status (all files) ─────────────────────────────────
    ws3 = wb.create_sheet("Node Status")
    node_hdrs = ["File Path", "Type"] + nodes + ["Status"]
    node_widths = [55, 8] + [16] * len(nodes) + [22]
    _hdr_row(ws3, 1, node_hdrs, node_widths)
    ws3.freeze_panes = "C2"

    for row_i, af in enumerate(result.files, 2):
        absent_nodes = [n for n in nodes if n not in af.present_in]
        if af.mismatch_count > 0 and af.absent_count > 0:
            row_fill = BOTH_FILL
            status   = "Diff + Absent/Missing"
        elif af.mismatch_count > 0:
            row_fill = RED_FILL
            status   = "Diff"
        elif af.absent_count > 0:
            row_fill = ORANGE_FILL
            status   = "Absent/Missing"
        else:
            row_fill = OK_FILL
            status   = "OK"

        _set_cell(ws3, row_i, 1, af.rel_path, font=NORMAL, fill=row_fill)
        _set_cell(ws3, row_i, 2, af.file_type.upper(),
                  font=NORMAL, fill=row_fill,
                  align=Alignment(horizontal="center", vertical="top"))
        for col_i, node in enumerate(nodes, 3):
            present = node in af.present_in
            val  = "✓" if present else "✗ absent"
            fnt  = GREEN_FONT if present else ORANGE_FONT
            _set_cell(ws3, row_i, col_i, val, font=fnt, fill=row_fill,
                      align=Alignment(horizontal="center", vertical="top"))
        _set_cell(ws3, row_i, 3 + len(nodes), status,
                  font=GREEN_FONT if status == "OK" else (RED_FONT if "Diff" in status else ORANGE_FONT),
                  fill=row_fill,
                  align=Alignment(horizontal="center", vertical="top"))

    # ── Sheet 4: Parameter Diffs ─────────────────────────────────────────
    import hashlib as _hashlib

    ws4 = wb.create_sheet("Parameter Diffs")
    YELLOW_BG   = PatternFill("solid", fgColor="FFF9C4")
    ABSENT_FILL = PatternFill("solid", fgColor="FFF3E0")  # orange for absent node cells

    param_diff_hdrs = ["File Path", "File Type", "Section", "Parameter Key"] + nodes + ["Note"]
    param_diff_widths = [50, 8, 20, 30] + [22] * len(nodes) + [20]
    _hdr_row(ws4, 1, param_diff_hdrs, param_diff_widths)
    ws4.freeze_panes = "A2"

    # Collect all mismatch params sorted by file path, section, key
    mismatch_params = []
    for af in result.files:
        for p in af.params:
            if p.has_mismatch:
                mismatch_params.append((af, p))
    mismatch_params.sort(key=lambda x: (x[0].rel_path, x[1].section or "", x[1].key or ""))

    for row_i, (af, p) in enumerate(mismatch_params, 2):
        note = "logical diff" if p.is_logical_diff else ""
        base_cols = [
            af.rel_path,
            af.file_type.upper(),
            p.section or "",
            p.key or p.compound,
        ]
        for col_i, val in enumerate(base_cols, 1):
            _set_cell(ws4, row_i, col_i, val, font=NORMAL, fill=RED_FILL)

        for ni, node in enumerate(nodes):
            col_i = 5 + ni
            node_val = (p.values or {}).get(node)
            if node_val is None:
                _set_cell(ws4, row_i, col_i, "\u2014absent\u2014",
                          font=Font(italic=True, color="E65100", name="Calibri", size=10),
                          fill=ABSENT_FILL,
                          align=Alignment(horizontal="center", vertical="top"))
            else:
                # Duplicate in section: every active value with its source line
                dups = (p.dup_values or {}).get(node)
                node_lines = p.lines.get(node, [])
                text = (" | ".join(f"{v} (L{ln})" for v, ln in zip(dups, node_lines))
                        + (f" → L{node_lines[-1]} used" if node_lines else "")
                        if dups else str(node_val))
                _set_cell(ws4, row_i, col_i, text, font=NORMAL, fill=RED_FILL)

        note_col = 5 + len(nodes)
        _set_cell(ws4, row_i, note_col, note, font=NORMAL, fill=RED_FILL)

    if not mismatch_params:
        ws4.cell(row=2, column=1, value="No parameter mismatches found.").font = GREEN_FONT

    # ── Sheet 5: Checksum Check ───────────────────────────────────────────
    ws5 = wb.create_sheet("Checksum Check")
    chk_hdrs = ["File Path", "File Type", "Note"] + nodes
    chk_widths = [50, 8, 45] + [22] * len(nodes)
    _hdr_row(ws5, 1, chk_hdrs, chk_widths)
    ws5.freeze_panes = "A2"

    chk_row_i = 2
    for af in result.files:
        # Only check files with no param mismatches and no absent nodes
        if af.mismatch_count != 0 or af.absent_count != 0:
            continue
        if af.file_type in ("binary", "error"):
            continue
        hashes: dict = {}
        for node in nodes:
            node_dir = (result.node_dirs or {}).get(node, "")
            fpath = os.path.join(node_dir, af.rel_path)
            try:
                hashes[node] = _hashlib.sha256(open(fpath, "rb").read()).hexdigest()
            except OSError:
                hashes[node] = None
        # Only include if hashes differ
        unique_hashes = {h for h in hashes.values() if h is not None}
        if len(unique_hashes) <= 1:
            continue
        note = "Raw checksums differ \u2014 possible encoding/line-ending difference"
        _set_cell(ws5, chk_row_i, 1, af.rel_path, font=NORMAL, fill=YELLOW_BG)
        _set_cell(ws5, chk_row_i, 2, af.file_type.upper(), font=NORMAL, fill=YELLOW_BG,
                  align=Alignment(horizontal="center", vertical="top"))
        _set_cell(ws5, chk_row_i, 3, note, font=NORMAL, fill=YELLOW_BG)
        for ni, node in enumerate(nodes):
            col_i = 4 + ni
            h = hashes.get(node)
            _set_cell(ws5, chk_row_i, col_i, h or "N/A", font=NORMAL, fill=YELLOW_BG)
        chk_row_i += 1

    if chk_row_i == 2:
        ws5.cell(row=2, column=1, value="No raw checksum differences found for matched files.").font = GREEN_FONT

    # ── Sheet 6: Absent Files ─────────────────────────────────────────────
    ws6 = wb.create_sheet("Absent Files")
    absent_hdrs = ["File Path", "File Type", "Present In", "Absent From", "Mismatch Count"]
    absent_widths = [55, 8, 30, 30, 14]
    _hdr_row(ws6, 1, absent_hdrs, absent_widths)
    ws6.freeze_panes = "A2"

    absent_files = sorted(
        [af for af in result.files if af.absent_count > 0],
        key=lambda f: f.rel_path
    )
    for row_i, af in enumerate(absent_files, 2):
        absent_nodes = [n for n in nodes if n not in af.present_in]
        if af.mismatch_count > 0 and af.absent_count > 0:
            row_fill = BOTH_FILL
        else:
            row_fill = ORANGE_FILL
        _set_cell(ws6, row_i, 1, af.rel_path, font=NORMAL, fill=row_fill)
        _set_cell(ws6, row_i, 2, af.file_type.upper(), font=NORMAL, fill=row_fill,
                  align=Alignment(horizontal="center", vertical="top"))
        _set_cell(ws6, row_i, 3, ", ".join(af.present_in), font=NORMAL, fill=row_fill, align=WRAP)
        _set_cell(ws6, row_i, 4, ", ".join(absent_nodes), font=ORANGE_FONT, fill=row_fill, align=WRAP)
        _set_cell(ws6, row_i, 5, af.mismatch_count or "", font=NORMAL, fill=row_fill,
                  align=Alignment(horizontal="center", vertical="top"))

    if not absent_files:
        ws6.cell(row=2, column=1, value="No absent files found.").font = GREEN_FONT

    # ── Sheet 7: Skipped Backups ──────────────────────────────────────────
    ws7 = wb.create_sheet("Skipped Backups")
    skip_hdrs = ["Relative Path", "Reason", "Base Dir"]
    skip_widths = [55, 40, 40]
    _hdr_row(ws7, 1, skip_hdrs, skip_widths)
    ws7.freeze_panes = "A2"

    skipped_list = result.skipped_backups or []
    if skipped_list:
        for row_i, entry in enumerate(skipped_list, 2):
            _set_cell(ws7, row_i, 1, entry.get("rel_path", ""), font=NORMAL)
            _set_cell(ws7, row_i, 2, entry.get("reason", ""), font=NORMAL, align=WRAP)
            _set_cell(ws7, row_i, 3, entry.get("base_dir", ""), font=NORMAL)
    else:
        ws7.cell(row=2, column=1, value="No backup files were skipped.").font = GREEN_FONT

    # ── Sheet 8: Filtered Files ───────────────────────────────────────────
    ws8 = wb.create_sheet("Filtered Files")
    filt_hdrs = ["Relative Path", "Reason", "Base Dir"]
    filt_widths = [55, 40, 40]
    _hdr_row(ws8, 1, filt_hdrs, filt_widths)
    ws8.freeze_panes = "A2"

    filtered_list = result.filtered_files or []
    if filtered_list:
        for row_i, entry in enumerate(filtered_list, 2):
            _set_cell(ws8, row_i, 1, entry.get("rel_path", ""), font=NORMAL)
            _set_cell(ws8, row_i, 2, entry.get("reason", ""), font=NORMAL, align=WRAP)
            _set_cell(ws8, row_i, 3, entry.get("base_dir", ""), font=NORMAL)
    else:
        ws8.cell(row=2, column=1, value="No files were excluded by filter.").font = GREEN_FONT

    # ── Reorder sheets: Summary, Issues, Parameter Diffs, Checksum Check,
    #                   Absent Files, Node Status, Skipped Backups, Filtered Files
    desired_order = ["Summary", "Issues", "Parameter Diffs", "Checksum Check",
                     "Absent Files", "Node Status", "Skipped Backups", "Filtered Files"]
    for i, sheet_name in enumerate(desired_order):
        if sheet_name in wb.sheetnames:
            wb.move_sheet(sheet_name, offset=i - wb.sheetnames.index(sheet_name))

    xlsx_path = os.path.join(run_dir, "audit_diffs.xlsx")
    wb.save(xlsx_path)
    return xlsx_path


def _write_html_parts(path: str, parts) -> None:
    """Validate and write a page given as (head, data_js, tail) without joining it."""
    head, data_js, tail = parts
    _validate_html_parts(head, data_js, tail, path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(head)
        f.write(data_js)
        f.write(tail)


def write_audit_html(result: "AuditResult", run_dir: str) -> str:
    """Write the audit report HTML.

    Phase 3.1: when the serialised report exceeds 22 MB, the report is split
    into numbered part files (``audit_report_p01.html``, ``p02.html``, …) with
    an index page (``audit_report.html``).  For small reports a single file is
    written as before.

    Returns the path to the primary output file (index page when paginated,
    single file otherwise).
    """
    os.makedirs(run_dir, exist_ok=True)

    # Generate formatted XLSX alongside the HTML report
    _write_diffs_xlsx(result, run_dir)

    parts_chunks = _split_into_parts(result)

    if len(parts_chunks) == 1:
        # Single-part: write the classic single-file report
        out_path = os.path.join(run_dir, "audit_report.html")
        _write_html_parts(out_path, _render_html_parts(result, files_js=parts_chunks[0]))
        return out_path

    # Multi-part: write one file per chunk and an index page
    total_parts = len(parts_chunks)
    parts_meta = []
    for i, chunk in enumerate(parts_chunks, 1):
        label    = f"Part {i} of {total_parts}"
        filename = f"audit_report_p{i:02d}.html"
        parts_meta.append({"label": f"Part {i}", "url": filename, "files": chunk})

    # Pre-compute per-part diff/absent stats for part-nav badges
    _part_stats = [
        {
            "diffs":  sum(1 for f in m["files"] if f.get("mismatchCount", 0) > 0),
            "absent": sum(1 for f in m["files"] if (f.get("absentCount") or 0) > 0),
        }
        for m in parts_meta
    ]

    part_pages: list = []
    for i, meta in enumerate(parts_meta, 1):
        pagination = {
            "current": i,
            "total":   total_parts,
            "parts":   [
                {"label": m["label"],
                 "url":   "#" if j + 1 == i else m["url"],
                 "diffs":  _part_stats[j]["diffs"],
                 "absent": _part_stats[j]["absent"]}
                for j, m in enumerate(parts_meta)
            ],
        }
        part_path = os.path.join(run_dir, meta["url"])
        _write_html_parts(part_path, _render_html_parts(
            result, files_js=meta["files"], pagination=pagination))
        part_pages.append(part_path)

    # Write the index page
    index_path = os.path.join(run_dir, "audit_report.html")
    index_html = _build_index_html(result, parts_meta)
    _validate_html(index_html, index_path)
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(index_html)

    return index_path
