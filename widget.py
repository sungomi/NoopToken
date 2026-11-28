import argparse
import base64
import hashlib
import json
import logging
import os
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
import requests

from providers import (
    AGY_SCOPES,
    CLAUDE_CLIENT_ID,
    CLAUDE_SCOPES,
    CODEX_CLIENT_ID,
    CODEX_SCOPES,
    clear_provider_auth,
    fetch_all_quotas,
    get_agy_oauth_client,
    invalidate_provider_cache,
    load_config,
    save_config,
)
from updater import (
    APP_EN_NAME,
    APP_NAME,
    APP_VERSION,
    check_for_update,
    get_update_status,
    start_update,
)

OAUTH_STATE: Dict[str, Any] = {
    "agy_verifier": "",
    "claude_verifier": "",
    "claude_state": "",
    "codex_verifier": "",
    "codex_state": "",
    "server_port": 17890,
    "popup_procs": [],
}

SUCCESS_CLOSE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>로그인 완료</title></head>
<body style="background:#080b11;color:#10b981;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
  <div style="text-align:center;padding:24px;">
    <div style="font-size:36px;margin-bottom:10px;">✓</div>
    <h2 style="margin:0 0 8px 0;">로그인 연동 완료</h2>
    <p style="color:#94a3b8;font-size:13px;margin:0;">위젯에 공식 모델 그룹별 사용량이 자동으로 표시됩니다.<br/>이 창은 자동으로 닫힙니다.</p>
  </div>
  <script>setTimeout(() => { window.open('', '_self', ''); window.close(); }, 300);</script>
</body>
</html>"""

UI_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NoopToken</title>
<style>
  :root {
    --bg: #f5f6fa;
    --bg-subtle: #eceef6;
    --surface: #ffffff;
    --surface-2: #f8f9fd;
    --sidebar: rgba(255, 255, 255, 0.78);
    --border: rgba(15, 23, 42, 0.075);
    --border-strong: rgba(15, 23, 42, 0.14);
    --text: #0f172a;
    --text-2: #475569;
    --text-3: #94a3b8;
    --accent: #5b67f5;
    --accent-soft: rgba(91, 103, 245, 0.10);
    --accent-ring: rgba(91, 103, 245, 0.22);
    --peach: #f29b60;
    --ok: #10b981;
    --ok-soft: rgba(16, 185, 129, 0.12);
    --warn: #f59e0b;
    --warn-soft: rgba(245, 158, 11, 0.13);
    --danger: #ef4444;
    --danger-soft: rgba(239, 68, 68, 0.12);
    --track: #e8ebf4;
    --shadow-card: 0 1px 2px rgba(15, 23, 42, 0.04), 0 6px 20px rgba(15, 23, 42, 0.045);
    --shadow-hover: 0 2px 6px rgba(15, 23, 42, 0.06), 0 12px 28px rgba(15, 23, 42, 0.075);
    --inset-top: inset 0 1px 0 rgba(255, 255, 255, 0.9);
    --radius: 18px;
    --font: "Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Malgun Gothic", sans-serif;
    color-scheme: light;
  }

  :root[data-theme="dark"] {
    --bg: #0b0d15;
    --bg-subtle: #111422;
    --surface: #141826;
    --surface-2: #1a1f31;
    --sidebar: rgba(17, 20, 34, 0.86);
    --border: rgba(255, 255, 255, 0.07);
    --border-strong: rgba(255, 255, 255, 0.14);
    --text: #f1f5f9;
    --text-2: #94a3b8;
    --text-3: #64748b;
    --accent: #818cf8;
    --accent-soft: rgba(129, 140, 248, 0.16);
    --accent-ring: rgba(129, 140, 248, 0.30);
    --peach: #f29b60;
    --ok: #34d399;
    --ok-soft: rgba(52, 211, 153, 0.14);
    --warn: #fbbf24;
    --warn-soft: rgba(251, 191, 36, 0.14);
    --danger: #f87171;
    --danger-soft: rgba(248, 113, 113, 0.15);
    --track: rgba(255, 255, 255, 0.08);
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.35), 0 10px 26px rgba(0, 0, 0, 0.28);
    --shadow-hover: 0 4px 12px rgba(0, 0, 0, 0.45), 0 16px 34px rgba(0, 0, 0, 0.36);
    --inset-top: inset 0 1px 0 rgba(255, 255, 255, 0.055);
    color-scheme: dark;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; -webkit-user-select: none; }
  html, body { height: 100%; }
  body {
    font-family: var(--font);
    font-size: 13px;
    color: var(--text);
    background: var(--bg);
    -webkit-font-smoothing: antialiased;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.012em;
    overflow: hidden;
  }
  input { user-select: text; -webkit-user-select: text; }
  button { font: inherit; color: inherit; }

  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 99px; }

  .app { display: flex; height: 100vh; width: 100vw; }

  /* ---------------- Sidebar ---------------- */
  .sidebar {
    width: 220px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    padding: 20px 14px 14px;
    background: var(--sidebar);
    border-right: 1px solid var(--border);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
  }
  body.compact .sidebar { display: none; }

  .brand {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 2px 8px 22px;
  }
  .brand-logo {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    object-fit: cover;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.16);
    flex-shrink: 0;
  }
  .brand-title-wrap { display: flex; flex-direction: column; gap: 1px; }
  .brand-name { font-size: 15.5px; font-weight: 800; letter-spacing: -0.025em; }
  .brand-sub { font-size: 10.5px; color: var(--text-3); font-weight: 500; }

  .nav { display: flex; flex-direction: column; gap: 4px; }
  .nav-item {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9.5px 12px;
    border: 0;
    border-radius: 11px;
    background: transparent;
    color: var(--text-2);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
    transition: background 0.15s ease, color 0.15s ease;
  }
  .nav-item:hover { background: var(--surface-2); color: var(--text); }
  .nav-item.active {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 700;
  }
  .nav-item svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
  .nav-count {
    margin-left: auto;
    font-size: 10.5px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 99px;
    background: var(--bg-subtle);
    color: var(--text-2);
  }
  .nav-item.active .nav-count { background: var(--accent); color: #ffffff; }

  .sidebar-spacer { flex: 1; }

  .sidebar-footer {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }
  .sidebar-btn-row { display: flex; gap: 6px; }
  .collapse-btn {
    flex: 1;
    padding: 8.5px 10px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    font-size: 12px;
    font-weight: 650;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    box-shadow: var(--shadow-card);
    transition: border-color 0.15s ease, color 0.15s ease, transform 0.12s ease;
  }
  .collapse-btn:hover { border-color: var(--accent); color: var(--accent); transform: translateY(-1px); }
  .theme-btn {
    width: 34px;
    flex-shrink: 0;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-2);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-card);
    transition: border-color 0.15s ease, color 0.15s ease;
  }
  .theme-btn:hover { border-color: var(--accent); color: var(--accent); }
  .theme-btn svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }

  .sidebar-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 10.5px;
    color: var(--text-3);
    padding: 2px 4px 0;
  }
  .version-link { cursor: pointer; font-weight: 600; }
  .version-link:hover { color: var(--accent); }

  /* ---------------- Compact Header (Mini Widget) ---------------- */
  .compact-header {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 10px 14px;
    background: var(--sidebar);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  body.compact .compact-header { display: flex; }
  .compact-brand { display: flex; align-items: center; gap: 8px; font-weight: 750; font-size: 13.5px; letter-spacing: -0.02em; }
  .compact-logo { width: 22px; height: 22px; border-radius: 6px; }
  .compact-actions { display: flex; align-items: center; gap: 5px; }

  /* ---------------- Main Area ---------------- */
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 0;
  }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 20px 26px 12px;
    flex-shrink: 0;
  }
  body.compact .topbar { display: none; }
  .page-title-wrap { display: flex; flex-direction: column; gap: 2px; }
  .page-title { font-size: 20px; font-weight: 800; letter-spacing: -0.03em; }
  .page-sub { font-size: 11.5px; color: var(--text-3); font-weight: 500; }

  .page-actions { display: flex; align-items: center; gap: 7px; }

  /* Segmented Control */
  .seg-ctrl {
    display: inline-flex;
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 2.5px;
    gap: 2px;
  }
  .seg-btn {
    border: 0;
    background: transparent;
    color: var(--text-2);
    font-size: 11.5px;
    font-weight: 600;
    padding: 5px 10px;
    border-radius: 7.5px;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }
  .seg-btn.active {
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
    font-weight: 700;
  }

  .pill-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text-2);
    border-radius: 10px;
    height: 31px;
    padding: 0 11px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    transition: all 0.14s ease;
    white-space: nowrap;
  }
  .pill-btn:hover { border-color: var(--border-strong); color: var(--text); }
  .pill-btn.active { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
  .pill-btn:disabled { opacity: 0.7; cursor: default; color: var(--accent); min-width: 34px; }
  .pill-btn svg { width: 13px; height: 13px; stroke: currentColor; fill: none; stroke-width: 2; pointer-events: none; }
  body.compact .pill-btn { height: 26px; padding: 0 8.5px; font-size: 11px; border-radius: 7px; }

  .scroll-area {
    flex: 1;
    overflow-y: auto;
    padding: 4px 26px 26px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  body.compact .scroll-area { padding: 10px 12px 14px; gap: 10px; }

  .update-banner {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 12px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-ring);
    font-size: 12px;
    font-weight: 650;
  }
  .update-banner.show { display: flex; }
  .update-apply-btn {
    background: var(--accent); color: #ffffff; border: none; border-radius: 8px;
    padding: 5px 12px; font-size: 11.5px; font-weight: 700; cursor: pointer;
  }
  .update-close-btn { background: transparent; border: none; color: var(--text-2); cursor: pointer; padding: 2px 5px; }

  /* ---------------- Status Ribbon (Replaces cluttered 3-box + 4-box duplication) ---------------- */
  .status-ribbon {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    padding: 11px 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    box-shadow: var(--shadow-card), var(--inset-top);
  }
  body.compact .status-ribbon { display: none; }
  .ribbon-stat {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    padding-right: 12px;
    border-right: 1px solid var(--border);
  }
  .ribbon-stat:last-child { padding-right: 0; border-right: 0; }
  .ribbon-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 3px var(--ok-soft); flex-shrink: 0; }
  .ribbon-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .ribbon-label { font-size: 10.5px; color: var(--text-3); font-weight: 600; white-space: nowrap; }
  .ribbon-val { font-size: 12.5px; font-weight: 750; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* ---------------- Provider Cards Grid ---------------- */
  .cards {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    align-items: start;
  }
  body.compact .cards { grid-template-columns: 1fr; gap: 10px; }
  @media (max-width: 760px) { .cards { grid-template-columns: 1fr; } }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow-card), var(--inset-top);
    overflow: hidden;
    transition: border-color 0.16s ease, box-shadow 0.16s ease;
  }
  body.compact .card { border-radius: 14px; }
  .card:hover { border-color: var(--border-strong); box-shadow: var(--shadow-hover), var(--inset-top); }
  .card.dragging { opacity: 0.92; border-color: var(--accent); }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 14px 16px;
    cursor: grab;
  }
  body.compact .card-header { padding: 11px 13px; }
  .card-header:active { cursor: grabbing; }

  .provider-left { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
  .drag-grip { width: 8px; height: 14px; opacity: 0; transition: opacity 0.15s ease; display: inline-flex; align-items: center; flex-shrink: 0; color: var(--text-3); }
  .card:hover .drag-grip, .group-box:hover .drag-grip { opacity: 0.65; }
  .drag-grip svg { width: 8px; height: 14px; fill: currentColor; }

  .brand-icon {
    width: 32px; height: 32px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  body.compact .brand-icon { width: 26px; height: 26px; border-radius: 8px; }
  .brand-icon svg { width: 16px; height: 16px; }
  .brand-antigravity { background: rgba(91, 103, 245, 0.12); color: #5b67f5; }
  .brand-claude { background: rgba(242, 155, 96, 0.18); color: #d97706; }
  .brand-cursor { background: rgba(14, 165, 233, 0.13); color: #0284c7; }
  .brand-codex { background: rgba(16, 185, 129, 0.13); color: #10b981; }

  .provider-title-stack { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .provider-name-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .provider-info-btn {
    background: transparent; border: none; padding: 0; cursor: pointer;
    display: inline-flex; align-items: center; gap: 6px; min-width: 0;
  }
  .provider-info-btn:hover .provider-name { color: var(--accent); }
  .provider-name { font-weight: 750; font-size: 14.5px; letter-spacing: -0.02em; white-space: nowrap; }
  .running-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 2.5px var(--ok-soft); flex-shrink: 0; }
  .plan-sub { font-size: 11px; color: var(--text-3); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .card-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .card-actions {
    display: flex; align-items: center; gap: 4px;
    opacity: 0.45; transition: opacity 0.15s ease;
  }
  .card:hover .card-actions { opacity: 1; }
  .icon-action-btn {
    width: 24px; height: 24px; border-radius: 7px;
    border: 1px solid transparent; background: transparent;
    color: var(--text-2); font-size: 11.5px; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    transition: all 0.14s ease;
  }
  .icon-action-btn:hover { background: var(--surface-2); border-color: var(--border); color: var(--text); }
  .icon-action-btn:disabled { opacity: 1; color: var(--accent); font-weight: 700; font-size: 10.5px; cursor: default; }

  .card-summary-badge {
    font-size: 13px; font-weight: 800; padding: 3px 9px; border-radius: 99px;
    white-space: nowrap; letter-spacing: -0.02em;
  }
  .chevron-badge {
    width: 22px; height: 22px; border-radius: 7px; color: var(--text-3);
    display: flex; align-items: center; justify-content: center; font-size: 10px;
    transition: transform 0.2s ease, background 0.15s ease;
  }
  .card-header:hover .chevron-badge { background: var(--surface-2); color: var(--text); }
  .chevron-badge.folded { transform: rotate(-90deg); }

  .card-body { padding: 0 14px 14px; }
  body.compact .card-body { padding: 0 11px 11px; }
  .card-body.folded { display: none; }
  .boxes-list { display: flex; flex-direction: column; gap: 10px; }

  /* ---------------- Model Group Tile (Radial Ring + Precision Bars) ---------------- */
  .group-box {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 12px 13px;
    transition: border-color 0.15s ease;
  }
  body.compact .group-box { padding: 10px 11px; border-radius: 11px; }
  .group-box:hover { border-color: var(--border-strong); }
  .group-box.dragging { border-color: var(--accent); }

  .group-tile {
    display: flex;
    align-items: center;
    gap: 13px;
  }
  .ring-wrap {
    position: relative;
    width: 50px;
    height: 50px;
    flex-shrink: 0;
    cursor: pointer;
  }
  body.compact .ring-wrap { width: 44px; height: 44px; }
  .ring-wrap svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  .ring-center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }
  .ring-num { font-size: 12px; font-weight: 800; letter-spacing: -0.03em; }
  .ring-unit { font-size: 8.5px; color: var(--text-3); font-weight: 600; margin-top: 1px; }

  .group-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .box-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    cursor: grab;
  }
  .box-title-wrap { display: flex; align-items: center; gap: 5px; min-width: 0; }
  .box-title-btn {
    background: transparent; border: none; padding: 1px 4px; margin: -1px -4px;
    border-radius: 6px; font-weight: 700; font-size: 12.5px; color: var(--text);
    cursor: pointer; display: inline-flex; align-items: center; gap: 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .box-title-btn:hover { color: var(--accent); background: var(--accent-soft); }
  .info-dot { font-size: 10.5px; color: var(--text-3); flex-shrink: 0; }
  .box-chevron { font-size: 9.5px; color: var(--text-3); transition: transform 0.2s ease; cursor: pointer; }
  .box-chevron.folded { transform: rotate(-90deg); }

  .box-body { display: flex; flex-direction: column; gap: 7px; }
  .box-body.folded { display: none; }

  .bar-row { display: flex; flex-direction: column; gap: 4px; }
  .bar-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 11px; }
  .bar-left { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
  .bar-tag {
    font-size: 9.5px; font-weight: 700; padding: 1px 5.5px; border-radius: 5px;
    background: var(--bg-subtle); color: var(--text-2); white-space: nowrap;
  }
  .bar-reset { font-size: 10.5px; color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar-val { font-weight: 750; font-size: 11.5px; white-space: nowrap; flex-shrink: 0; }
  .bar-track { height: 5px; background: var(--track); border-radius: 99px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 99px; transition: width 0.4s cubic-bezier(0.22, 1, 0.36, 1); }

  /* ---------------- Accounts & Settings Views ---------------- */
  .accounts-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
  }
  @media (max-width: 720px) { .accounts-grid { grid-template-columns: 1fr; } }
  .account-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    box-shadow: var(--shadow-card), var(--inset-top);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .account-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .account-id { display: flex; align-items: center; gap: 11px; min-width: 0; }
  .account-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .account-title { font-weight: 750; font-size: 14px; display: flex; align-items: center; gap: 6px; }
  .account-sub { font-size: 11.5px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .status-pill {
    font-size: 10.5px; font-weight: 700; padding: 3px 9px; border-radius: 99px;
    background: var(--bg-subtle); color: var(--text-3); white-space: nowrap;
  }
  .status-pill.linked { background: var(--ok-soft); color: var(--ok); }
  .account-actions { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }

  .login-btn {
    background: var(--accent); color: #ffffff; border: none; border-radius: 10px;
    padding: 9px 14px; font-size: 12px; font-weight: 700; cursor: pointer; width: 100%;
    transition: opacity 0.15s ease;
  }
  .login-btn:hover { opacity: 0.9; }
  .paste-box { display: none; gap: 6px; }
  .paste-box.show { display: flex; }
  .paste-input {
    flex: 1; background: var(--surface-2); border: 1px solid var(--border);
    color: var(--text); border-radius: 9px; padding: 7px 10px; font-size: 11.5px; outline: none;
  }
  .paste-input:focus { border-color: var(--accent); }
  .paste-submit {
    background: var(--accent); color: #fff; border: none; border-radius: 9px;
    padding: 7px 12px; font-weight: 700; font-size: 11.5px; cursor: pointer;
  }

  .settings-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 18px 20px; display: flex; flex-direction: column; gap: 16px;
    box-shadow: var(--shadow-card), var(--inset-top);
  }
  .setting-row {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    padding-bottom: 14px; border-bottom: 1px solid var(--border);
  }
  .setting-row:last-child { padding-bottom: 0; border-bottom: 0; }
  .setting-title { font-weight: 700; font-size: 13.5px; }
  .setting-desc { font-size: 11.5px; color: var(--text-3); margin-top: 2px; }

  .empty-state {
    grid-column: 1 / -1;
    background: var(--surface); border: 1px dashed var(--border-strong); border-radius: var(--radius);
    padding: 36px 20px; text-align: center; display: flex; flex-direction: column; gap: 10px; align-items: center;
  }

  /* ---------------- Modal ---------------- */
  .info-modal-backdrop {
    position: fixed; inset: 0; background: rgba(10, 12, 22, 0.52);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    display: none; align-items: center; justify-content: center; padding: 18px; z-index: 100;
  }
  .info-modal-backdrop.show { display: flex; }
  .info-modal-card {
    width: 100%; max-width: 360px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 18px; padding: 18px 20px; box-shadow: var(--shadow-hover);
    display: flex; flex-direction: column; gap: 12px;
  }
  .info-modal-head { display: flex; align-items: center; justify-content: space-between; }
  .info-modal-title { font-size: 14.5px; font-weight: 750; }
  .info-modal-close {
    background: var(--surface-2); border: 1px solid var(--border); color: var(--text-2);
    border-radius: 8px; width: 26px; height: 26px; cursor: pointer; font-size: 11px;
  }
  .info-modal-body { display: flex; flex-direction: column; gap: 7px; max-height: 270px; overflow-y: auto; }
  .info-modal-row {
    display: flex; justify-content: space-between; align-items: center; gap: 10px;
    padding: 9px 11px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--border);
    font-size: 12px;
  }
  .info-modal-label { color: var(--text-2); font-weight: 600; }
  .info-modal-val { font-weight: 700; text-align: right; word-break: break-all; }
  .info-modal-item {
    padding: 8px 11px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--border);
    font-size: 12px; font-weight: 550;
  }
  .info-modal-note {
    margin-top: 2px; padding: 9px 11px; border-radius: 10px;
    background: var(--accent-soft); color: var(--text-2); font-size: 11px; line-height: 1.5;
  }

  .view-panel { display: none; flex-direction: column; gap: 14px; }
  .view-panel.active { display: flex; }
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <img src="/assets/icon.png" class="brand-logo" alt="NoopToken" />
      <div class="brand-title-wrap">
        <span class="brand-name">NoopToken</span>
        <span class="brand-sub">AI Quota Monitor</span>
      </div>
    </div>

    <nav class="nav">
      <button class="nav-item active" id="navDashboard" onclick="switchTab('dashboard')">
        <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></svg>
        <span>대시보드</span>
      </button>
      <button class="nav-item" id="navAccounts" onclick="switchTab('accounts')">
        <svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <span>계정 연동</span>
        <span class="nav-count" id="linkedCountBadge">0</span>
      </button>
      <button class="nav-item" id="navSettings" onclick="switchTab('settings')">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        <span>설정</span>
      </button>
    </nav>

    <div class="sidebar-spacer"></div>

    <div class="sidebar-footer">
      <div class="sidebar-btn-row">
        <button class="collapse-btn" onclick="toggleCompact()">미니 위젯</button>
        <button class="theme-btn" id="btnThemeToggle" onclick="toggleTheme()" title="라이트 / 다크 테마 전환"></button>
      </div>
      <div class="sidebar-meta">
        <span class="version-link" id="appVersionBadge" onclick="checkForUpdates(true)" title="업데이트 확인">v__APP_VERSION__</span>
        <span id="updatedAt">동기화 중</span>
      </div>
    </div>
  </aside>

  <main class="main">
    <div class="compact-header pywebview-drag-region">
      <div class="compact-brand">
        <img src="/assets/icon.png" class="compact-logo" alt="NoopToken" />
        <span>NoopToken</span>
      </div>
      <div class="compact-actions">
        <button class="pill-btn active" id="btnDisplayModeCompact" onclick="toggleDisplayMode()">사용량</button>
        <button class="pill-btn" id="btnGlobalRefreshCompact" onmousedown="event.stopPropagation()" onpointerdown="event.stopPropagation()" onclick="manualGlobalRefresh()" title="새로고침 (5초 쿨다운)">
          <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>
        </button>
        <button class="pill-btn" onclick="toggleCompact()" title="전체 창으로 확장">확장</button>
      </div>
    </div>

    <header class="topbar">
      <div class="page-title-wrap">
        <h1 class="page-title" id="pageTitle">대시보드</h1>
        <span class="page-sub" id="pageSub">연동된 AI 모델별 실시간 한도와 리셋 일정을 한눈에 확인합니다</span>
      </div>
      <div class="page-actions">
        <div class="seg-ctrl" id="modeSegCtrl">
          <button class="seg-btn active" id="segUsed" onclick="setDisplayMode('used')">사용량</button>
          <button class="seg-btn" id="segRem" onclick="setDisplayMode('remaining')">잔여량</button>
        </div>
        <button class="pill-btn" id="btnGlobalRefresh" onclick="manualGlobalRefresh()" title="전체 강제 새로고침 (5초 쿨다운)">
          <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>
          <span>새로고침</span>
        </button>
      </div>
    </header>

    <div class="scroll-area">
      <div class="update-banner" id="updateBanner">
        <span id="updateBannerText">새 버전이 있습니다</span>
        <div style="display:flex;align-items:center;gap:6px;">
          <button class="update-apply-btn" id="updateApplyBtn" onclick="triggerUpdate()">업데이트</button>
          <button class="update-close-btn" onclick="dismissUpdateBanner()">✕</button>
        </div>
      </div>

      <section class="view-panel active" id="viewDashboard">
        <div class="status-ribbon" id="statusRibbon"></div>
        <div class="cards" id="cardsContainer"></div>
      </section>

      <section class="view-panel" id="viewAccounts">
        <div class="accounts-grid" id="accountsContainer"></div>
      </section>

      <section class="view-panel" id="viewSettings">
        <div class="settings-card">
          <div class="setting-row">
            <div>
              <div class="setting-title">화면 테마</div>
              <div class="setting-desc">라이트 모드와 다크 모드를 자유롭게 전환합니다.</div>
            </div>
            <button class="pill-btn" id="btnThemeSettings" onclick="toggleTheme()">테마 전환</button>
          </div>
          <div class="setting-row">
            <div>
              <div class="setting-title">표시 기준</div>
              <div class="setting-desc">한도를 사용량(% 사용) 또는 잔여량(% 남음) 기준으로 표시합니다.</div>
            </div>
            <button class="pill-btn active" id="btnDisplayModeSettings" onclick="toggleDisplayMode()">사용량 기준</button>
          </div>
          <div class="setting-row">
            <div>
              <div class="setting-title">한도 임계치 · 리셋 알림</div>
              <div class="setting-desc">사용량 80%·90% 도달 및 한도 리셋 시 데스크톱 알림을 보냅니다.</div>
            </div>
            <button class="pill-btn active" id="btnNotify" onclick="toggleNotifications()">알림 켜짐</button>
          </div>
          <div class="setting-row">
            <div>
              <div class="setting-title">창 항상 위에 고정</div>
              <div class="setting-desc">다른 창 위에 NoopToken을 항상 띄워 둡니다.</div>
            </div>
            <button class="pill-btn" id="btnPin" onclick="togglePin()">꺼짐</button>
          </div>
          <div class="setting-row">
            <div>
              <div class="setting-title">버전 및 업데이트</div>
              <div class="setting-desc">현재 버전 v__APP_VERSION__ · GitHub 최신 릴리즈를 확인합니다.</div>
            </div>
            <button class="pill-btn" onclick="checkForUpdates(true)">업데이트 확인</button>
          </div>
        </div>
      </section>
    </div>
  </main>
</div>

<div class="info-modal-backdrop" id="infoModalBackdrop" onclick="closeInfoModal(event)">
  <div class="info-modal-card" onclick="event.stopPropagation()">
    <div class="info-modal-head">
      <span class="info-modal-title" id="infoModalTitle">상세 정보</span>
      <button class="info-modal-close" onclick="closeInfoModal()">✕</button>
    </div>
    <div class="info-modal-body" id="infoModalBody"></div>
  </div>
</div>

<script>
  let compactMode = false;
  let alwaysOnTop = false;
  let currentTab = "dashboard";
  let openPasteBoxes = {};
  let lastData = null;
  let isDragging = false;
  let notifyEnabled = true;

  let displayMode = localStorage.getItem("ai_quota_display_mode") || "used";
  let foldedCards = JSON.parse(localStorage.getItem("ai_quota_folded_cards") || "{}");
  let foldedBoxes = JSON.parse(localStorage.getItem("ai_quota_folded_boxes") || "{}");
  let cardOrder = JSON.parse(localStorage.getItem("ai_quota_card_order") || '["antigravity","claude","cursor","codex"]');
  let boxOrder = JSON.parse(localStorage.getItem("ai_quota_box_order") || "{}");
  let themePref = localStorage.getItem("nooptoken_theme") || "light";

  function applyTheme(t) {
    themePref = t;
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("nooptoken_theme", t);
    const btn = document.getElementById("btnThemeToggle");
    const sBtn = document.getElementById("btnThemeSettings");
    const sunSvg = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';
    const moonSvg = '<svg viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    if (btn) btn.innerHTML = t === "dark" ? sunSvg : moonSvg;
    if (sBtn) sBtn.textContent = t === "dark" ? "다크 모드" : "라이트 모드";
    fetch("/api/theme", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({theme: t})
    }).catch(() => {});
  }

  function toggleTheme() {
    applyTheme(themePref === "dark" ? "light" : "dark");
  }

  function saveStateToLocal() {
    localStorage.setItem("ai_quota_display_mode", displayMode);
    localStorage.setItem("ai_quota_folded_cards", JSON.stringify(foldedCards));
    localStorage.setItem("ai_quota_folded_boxes", JSON.stringify(foldedBoxes));
    localStorage.setItem("ai_quota_card_order", JSON.stringify(cardOrder));
    localStorage.setItem("ai_quota_box_order", JSON.stringify(boxOrder));
  }

  function switchTab(tab) {
    currentTab = tab;
    ["dashboard", "accounts", "settings"].forEach(t => {
      const nav = document.getElementById("nav" + t.charAt(0).toUpperCase() + t.slice(1));
      const view = document.getElementById("view" + t.charAt(0).toUpperCase() + t.slice(1));
      if (nav) nav.classList.toggle("active", t === tab);
      if (view) view.classList.toggle("active", t === tab);
    });
    const meta = {
      dashboard: ["대시보드", "연동된 AI 모델별 실시간 한도와 리셋 일정을 한눈에 확인합니다"],
      accounts: ["계정 연동", "AI 코딩 에이전트 계정을 연결하거나 상태를 관리합니다"],
      settings: ["설정", "테마, 알림, 표시 기준 및 업데이트를 설정합니다"]
    };
    const [title, sub] = meta[tab] || ["NoopToken", ""];
    document.getElementById("pageTitle").textContent = title;
    document.getElementById("pageSub").textContent = sub;
  }

  function updateModeHeaderUI() {
    document.getElementById("segUsed")?.classList.toggle("active", displayMode === "used");
    document.getElementById("segRem")?.classList.toggle("active", displayMode === "remaining");
    const cBtn = document.getElementById("btnDisplayModeCompact");
    if (cBtn) cBtn.textContent = displayMode === "used" ? "사용량" : "잔여량";
    const sBtn = document.getElementById("btnDisplayModeSettings");
    if (sBtn) sBtn.textContent = displayMode === "used" ? "사용량 기준" : "잔여량 기준";
  }

  function setDisplayMode(mode) {
    displayMode = mode;
    saveStateToLocal();
    updateModeHeaderUI();
    if (lastData) render(lastData);
  }

  function toggleDisplayMode() {
    setDisplayMode(displayMode === "used" ? "remaining" : "used");
  }

  function updateNotifyUI(enabled) {
    notifyEnabled = !!enabled;
    const btn = document.getElementById("btnNotify");
    if (!btn) return;
    btn.classList.toggle("active", notifyEnabled);
    btn.textContent = notifyEnabled ? "알림 켜짐" : "알림 꺼짐";
  }

  async function toggleNotifications() {
    const next = !notifyEnabled;
    updateNotifyUI(next);
    try {
      await fetch("/api/notify", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({enabled: next})
      });
    } catch (e) {}
  }

  function getDisplayMetric(remPct) {
    const r = Math.max(0, Math.min(100, Number(remPct) || 0));
    if (displayMode === "used") {
      const used = Math.round((100 - r) * 10) / 10;
      return { pct: used, width: used, tag: "사용" };
    }
    const rem = Math.round(r * 10) / 10;
    return { pct: rem, width: rem, tag: "남음" };
  }

  function getColor(remPct) {
    if (remPct >= 50) return "var(--ok)";
    if (remPct >= 20) return "var(--warn)";
    return "var(--danger)";
  }

  function getSoftBg(remPct) {
    if (remPct >= 50) return "var(--ok-soft)";
    if (remPct >= 20) return "var(--warn-soft)";
    return "var(--danger-soft)";
  }

  function shortBarTag(name) {
    const l = String(name || "").toLowerCase();
    if (l.includes("5시간") || l.includes("5h")) return "5h";
    if (l.includes("주간") || l.includes("weekly")) return "Weekly";
    if (l.includes("opus")) return "Opus";
    if (l.includes("sonnet")) return "Sonnet";
    return name;
  }

  function getBrandIconSvg(id) {
    if (id === "antigravity") return `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2L12 2Z"/></svg>`;
    if (id === "claude") return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6L5.6 18.4"/></svg>`;
    if (id === "cursor") return `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 3l16 7.5-7.2 2.3L10.5 20 4 3z"/></svg>`;
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 20 7 20 17 12 22 4 17 4 7 12 2"/><circle cx="12" cy="12" r="3"/></svg>`;
  }

  function getGripSvg() {
    return `<svg viewBox="0 0 8 14"><circle cx="2" cy="2.5" r="1.1"/><circle cx="6" cy="2.5" r="1.1"/><circle cx="2" cy="7" r="1.1"/><circle cx="6" cy="7" r="1.1"/><circle cx="2" cy="11.5" r="1.1"/><circle cx="6" cy="11.5" r="1.1"/></svg>`;
  }

  function shortName(id) {
    if (id === "antigravity") return "Antigravity";
    if (id === "claude") return "Claude";
    if (id === "cursor") return "Cursor";
    return "Codex";
  }

  function toggleCard(cardId) {
    foldedCards[cardId] = !foldedCards[cardId];
    saveStateToLocal();
    if (lastData) render(lastData);
  }

  function toggleBox(boxId) {
    foldedBoxes[boxId] = !foldedBoxes[boxId];
    saveStateToLocal();
    if (lastData) render(lastData);
  }

  async function fetchData(force = false, providerId = "") {
    try {
      let qs = "";
      if (force) qs = providerId ? `?force=1&provider=${encodeURIComponent(providerId)}` : "?force=1";
      const r = await fetch("/api/quotas" + qs, { cache: "no-store" });
      return await r.json();
    } catch (e) { return null; }
  }

  let loginPollTimer = null;

  async function openLogin(providerId, event) {
    if (event) event.stopPropagation();
    if (providerId === "claude" || providerId === "cursor") {
      openPasteBoxes[providerId] = true;
      if (lastData) render(lastData);
    }
    try { await fetch("/api/login/" + providerId, { method: "POST" }); } catch (e) {}
    if (loginPollTimer) clearInterval(loginPollTimer);
    let ticks = 0;
    loginPollTimer = setInterval(async () => {
      ticks++;
      await refreshNow(true);
      if (lastData && lastData.providers) {
        const p = lastData.providers.find(x => x.id === providerId);
        if (p && p.logged_in) { clearInterval(loginPollTimer); loginPollTimer = null; }
      }
      if (ticks > 45) { clearInterval(loginPollTimer); loginPollTimer = null; }
    }, 2000);
  }

  async function submitCodeOrToken(providerId, event) {
    if (event) event.stopPropagation();
    const inp = document.getElementById("input_" + providerId);
    const val = (inp ? inp.value : "").trim();
    if (!val) return;
    try {
      const r = await fetch("/api/submit_code", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({provider_id: providerId, code: val})
      });
      const res = await r.json();
      if (res && res.ok) {
        openPasteBoxes[providerId] = false;
        if (inp) inp.value = "";
        await refreshNow(true);
      } else {
        alert("인증에 실패했습니다. 복사한 값을 다시 확인해 주세요.");
      }
    } catch (e) {}
  }

  async function logoutProvider(providerId, event) {
    if (event) event.stopPropagation();
    try {
      await fetch("/api/logout/" + providerId, { method: "POST" });
      await refreshNow(true);
    } catch (e) {}
  }

  function renderStatusRibbon(orderedProviders) {
    const el = document.getElementById("statusRibbon");
    if (!el || compactMode) { if (el) el.innerHTML = ""; return; }
    const logged = orderedProviders.filter(p => p.logged_in);
    const running = orderedProviders.filter(p => p.running).map(p => shortName(p.id));
    let peak = null;
    logged.forEach(p => {
      const used = Math.round((100 - (Number(p.remaining_pct) || 0)) * 10) / 10;
      if (!peak || used > peak.used) peak = { name: p.name, used, rem: p.remaining_pct };
    });
    const nextReset = logged.find(p => p.reset_text) || logged[0];
    el.innerHTML = `
      <div class="ribbon-stat">
        <span class="ribbon-dot" style="background:${running.length ? 'var(--ok)' : 'var(--text-3)'};box-shadow:${running.length ? '0 0 0 3px var(--ok-soft)' : 'none'}"></span>
        <div class="ribbon-text">
          <span class="ribbon-label">실행 중</span>
          <span class="ribbon-val">${running.length ? running.join(" · ") : "없음"}</span>
        </div>
      </div>
      <div class="ribbon-stat">
        <div class="ribbon-text">
          <span class="ribbon-label">최대 사용</span>
          <span class="ribbon-val" style="color:${peak ? getColor(peak.rem) : 'var(--text-3)'}">${peak ? `${peak.name} ${peak.used}%` : "-"}</span>
        </div>
      </div>
      <div class="ribbon-stat">
        <div class="ribbon-text">
          <span class="ribbon-label">다음 리셋</span>
          <span class="ribbon-val">${nextReset ? `${nextReset.name} · ${nextReset.reset_text}` : "-"}</span>
        </div>
      </div>
    `;
  }

  function renderCardHtml(p) {
    const isCardFolded = !!foldedCards[p.id];
    const col = getColor(p.remaining_pct);
    const softBg = getSoftBg(p.remaining_pct);
    const cardMetric = getDisplayMetric(p.remaining_pct);
    const circ = 2 * Math.PI * 20;

    const boxesHtml = (p.boxes || []).map(box => {
      const isBoxFolded = !!foldedBoxes[box.id];
      const bCol = getColor(box.remaining_pct);
      const boxMetric = getDisplayMetric(box.remaining_pct);
      const dashOffset = circ * (1 - Math.max(0, Math.min(100, boxMetric.width)) / 100);

      const barsHtml = (box.bars || []).map(bar => {
        const barCol = getColor(bar.remaining_pct);
        const barMetric = getDisplayMetric(bar.remaining_pct);
        return `
          <div class="bar-row">
            <div class="bar-top">
              <span class="bar-left">
                <span class="bar-tag">${shortBarTag(bar.name)}</span>
                ${bar.reset_text ? `<span class="bar-reset">${bar.reset_text}</span>` : ""}
              </span>
              <span class="bar-val" style="color:${barCol}">${barMetric.pct}%</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill" style="width:${barMetric.width}%; background:${barCol}"></div>
            </div>
          </div>
        `;
      }).join("");

      return `
        <div class="group-box" data-box-id="${box.id}" data-provider-id="${p.id}">
          <div class="group-tile">
            <div class="ring-wrap" onclick="openBoxModelsModal('${p.id}', '${box.id}', event)" title="사용 가능 모델 보기">
              <svg viewBox="0 0 48 48">
                <circle cx="24" cy="24" r="20" fill="none" stroke="var(--track)" stroke-width="4.5" />
                <circle cx="24" cy="24" r="20" fill="none" stroke="${bCol}" stroke-width="4.5" stroke-linecap="round"
                  stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${dashOffset.toFixed(1)}" />
              </svg>
              <div class="ring-center">
                <span class="ring-num" style="color:${bCol}">${Math.round(boxMetric.pct)}%</span>
                <span class="ring-unit">${boxMetric.tag}</span>
              </div>
            </div>
            <div class="group-content">
              <div class="box-header" onpointerdown="startBoxDrag(event, '${p.id}', '${box.id}')">
                <div class="box-title-wrap">
                  <span class="drag-grip">${getGripSvg()}</span>
                  <button class="box-title-btn" onpointerdown="event.stopPropagation()" onclick="openBoxModelsModal('${p.id}', '${box.id}', event)" title="사용 가능한 모델 목록 보기">
                    <span>${box.title}</span>
                    ${box.subtitle ? `<span class="info-dot">ⓘ</span>` : ""}
                  </button>
                </div>
                <span class="box-chevron ${isBoxFolded ? 'folded' : ''}" onclick="toggleBox('${box.id}')">▾</span>
              </div>
              <div class="box-body ${isBoxFolded ? 'folded' : ''}">
                ${barsHtml}
              </div>
            </div>
          </div>
        </div>
      `;
    }).join("");

    return `
      <div class="card" data-card-id="${p.id}">
        <div class="card-header" onpointerdown="startCardDrag(event, '${p.id}')">
          <div class="provider-left">
            <span class="drag-grip">${getGripSvg()}</span>
            <div class="brand-icon brand-${p.id}">${getBrandIconSvg(p.id)}</div>
            <div class="provider-title-stack">
              <div class="provider-name-row">
                <button class="provider-info-btn" onpointerdown="event.stopPropagation()" onclick="openProviderInfoModal('${p.id}', event)" title="계정 및 플랜 확인">
                  <span class="provider-name">${p.name}</span>
                  ${p.running ? `<span class="running-dot" title="현재 PC에서 실행 중"></span>` : ""}
                </button>
              </div>
              <span class="plan-sub">${escapeHtml(p.plan || p.badge || "연동됨")}</span>
            </div>
          </div>
          <div class="card-right">
            <div class="card-actions">
              <button class="icon-action-btn provider-refresh-btn" data-refresh-provider="${p.id}" title="새로고침 (5초 쿨다운)" onpointerdown="event.stopPropagation()" onclick="refreshProvider('${p.id}', event)">↻</button>
            </div>
            <span class="card-summary-badge" style="color:${col};background:${softBg}">${cardMetric.pct}%</span>
            <div class="chevron-badge ${isCardFolded ? 'folded' : ''}">▾</div>
          </div>
        </div>
        <div class="card-body ${isCardFolded ? 'folded' : ''}">
          <div class="boxes-list" id="boxes_${p.id}">
            ${boxesHtml}
          </div>
        </div>
      </div>
    `;
  }

  function renderAccountsView(orderedProviders) {
    const accContainer = document.getElementById("accountsContainer");
    if (!accContainer) return;
    accContainer.innerHTML = orderedProviders.map(p => {
      const showPaste = openPasteBoxes[p.id] ? "show" : "";
      const placeholder = p.id === "claude"
        ? "로그인 후 화면에 뜬 인증코드 붙여넣기"
        : "WorkosCursorSessionToken 값 붙여넣기";
      const needsPaste = (p.id === "claude" || p.id === "cursor");
      if (p.logged_in) {
        return `
          <div class="account-card">
            <div class="account-top">
              <div class="account-id">
                <div class="brand-icon brand-${p.id}">${getBrandIconSvg(p.id)}</div>
                <div class="account-meta">
                  <div class="account-title">
                    <span>${p.name}</span>
                    ${p.running ? `<span class="running-dot" title="현재 PC에서 실행 중"></span>` : ""}
                  </div>
                  <div class="account-sub">${escapeHtml(p.account || "연동됨")} · ${escapeHtml(p.plan || p.badge || "")}</div>
                </div>
              </div>
              <span class="status-pill linked">연동됨</span>
            </div>
            <div class="account-actions">
              <button class="pill-btn" onclick="openProviderInfoModal('${p.id}', event)">상세 정보</button>
              <button class="pill-btn" onclick="openLogin('${p.id}', event)">재연동</button>
              <button class="pill-btn" style="color:var(--danger);" onclick="logoutProvider('${p.id}', event)">연동 해제</button>
            </div>
          </div>
        `;
      }
      return `
        <div class="account-card">
          <div class="account-top">
            <div class="account-id">
              <div class="brand-icon brand-${p.id}">${getBrandIconSvg(p.id)}</div>
              <div class="account-meta">
                <div class="account-title">
                  <span>${p.name}</span>
                  ${p.running ? `<span class="running-dot" title="현재 PC에서 실행 중"></span>` : ""}
                </div>
                <div class="account-sub">${escapeHtml(p.hint || "계정을 연동하면 실시간 한도를 표시합니다.")}</div>
              </div>
            </div>
            <span class="status-pill">미연동</span>
          </div>
          <div class="account-actions">
            <button class="login-btn" onclick="openLogin('${p.id}', event)">${p.login_label || (p.name + " 로그인")}</button>
          </div>
          ${needsPaste ? `
            <div class="paste-box ${showPaste}" id="paste_${p.id}">
              <input class="paste-input" id="input_${p.id}" placeholder="${placeholder}" onclick="event.stopPropagation()" />
              <button class="paste-submit" onclick="submitCodeOrToken('${p.id}', event)">연동</button>
            </div>
          ` : ""}
        </div>
      `;
    }).join("");
  }

  function render(data) {
    if (!data || !data.providers || isDragging) return;
    lastData = data;
    if (typeof data.notifications_enabled === "boolean") updateNotifyUI(data.notifications_enabled);
    const upEl = document.getElementById("updatedAt");
    if (upEl) upEl.textContent = data.updated_at;

    const savedInputs = {};
    ["claude", "cursor"].forEach(id => {
      const el = document.getElementById("input_" + id);
      if (el && el.value) savedInputs[id] = el.value;
    });

    const pMap = {};
    data.providers.forEach(p => { pMap[p.id] = p; });
    const orderedProviders = cardOrder.map(id => pMap[id]).filter(Boolean);
    data.providers.forEach(p => { if (!cardOrder.includes(p.id)) orderedProviders.push(p); });

    const linkedProviders = orderedProviders.filter(p => p.logged_in);
    const badge = document.getElementById("linkedCountBadge");
    if (badge) badge.textContent = `${linkedProviders.length}`;

    renderStatusRibbon(orderedProviders);
    renderAccountsView(orderedProviders);

    const container = document.getElementById("cardsContainer");
    if (linkedProviders.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div style="font-weight:750;font-size:15px;">연동된 AI 계정이 없습니다</div>
          <div style="font-size:12px;color:var(--text-3);">${compactMode ? '전체 창으로 확장해 계정을 먼저 연동하세요.' : '좌측 [계정 연동] 탭에서 계정을 연결하면 실시간 게이지가 표시됩니다.'}</div>
          <button class="pill-btn active" onclick="${compactMode ? 'toggleCompact()' : "switchTab('accounts')"}">${compactMode ? '전체 창으로 확장' : '계정 연동으로 이동'}</button>
        </div>
      `;
    } else {
      container.innerHTML = linkedProviders.map(p => renderCardHtml(p)).join("");
    }

    Object.keys(savedInputs).forEach(id => {
      const el = document.getElementById("input_" + id);
      if (el) el.value = savedInputs[id];
    });
    applyCooldownUI();
  }

  function startCardDrag(e, cardId) {
    if (e.button !== 0 || e.target.closest("button") || e.target.closest("input")) return;
    const cardEl = e.currentTarget.closest(".card");
    const container = cardEl.parentElement;
    if (!cardEl || !container) return;
    const startY = e.clientY;
    let moved = false;
    const onMove = (ev) => {
      if (!moved && Math.abs(ev.clientY - startY) < 6) return;
      if (!moved) { moved = true; isDragging = true; cardEl.classList.add("dragging"); }
      const cards = Array.from(container.querySelectorAll(".card")).filter(el => el !== cardEl);
      for (const other of cards) {
        const rect = other.getBoundingClientRect();
        if (ev.clientY < rect.top + rect.height / 2) { container.insertBefore(cardEl, other); return; }
      }
      container.appendChild(cardEl);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!moved) { toggleCard(cardId); return; }
      cardEl.classList.remove("dragging");
      isDragging = false;
      cardOrder = Array.from(container.querySelectorAll(".card")).map(el => el.dataset.cardId);
      syncOrderToBackend();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function startBoxDrag(e, providerId, boxId) {
    if (e.button !== 0 || e.target.closest("button")) return;
    e.stopPropagation();
    const boxEl = e.currentTarget.closest(".group-box");
    const listEl = boxEl.parentElement;
    if (!boxEl || !listEl) return;
    const startY = e.clientY;
    let moved = false;
    const onMove = (ev) => {
      if (!moved && Math.abs(ev.clientY - startY) < 6) return;
      if (!moved) { moved = true; isDragging = true; boxEl.classList.add("dragging"); }
      const boxes = Array.from(listEl.querySelectorAll(".group-box")).filter(el => el !== boxEl);
      for (const other of boxes) {
        const rect = other.getBoundingClientRect();
        if (ev.clientY < rect.top + rect.height / 2) { listEl.insertBefore(boxEl, other); return; }
      }
      listEl.appendChild(boxEl);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!moved) { toggleBox(boxId); return; }
      boxEl.classList.remove("dragging");
      isDragging = false;
      boxOrder[providerId] = Array.from(listEl.querySelectorAll(".group-box")).map(el => el.dataset.boxId);
      syncOrderToBackend();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  async function syncOrderToBackend() {
    saveStateToLocal();
    try {
      await fetch("/api/save_order", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({card_order: cardOrder, box_order: boxOrder})
      });
    } catch (e) {}
  }

  async function refreshNow(force = false, providerId = "") {
    if (isDragging) return;
    if (document.activeElement && document.activeElement.tagName === "INPUT") return;
    const data = await fetchData(force, providerId);
    if (data) render(data);
  }

  async function toggleCompact() {
    compactMode = !compactMode;
    document.body.classList.toggle("compact", compactMode);
    if (compactMode) switchTab("dashboard");
    if (lastData) render(lastData);
    try {
      await fetch("/api/window", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({compact: compactMode})
      });
    } catch (e) {}
  }

  async function togglePin() {
    alwaysOnTop = !alwaysOnTop;
    const btn = document.getElementById("btnPin");
    if (btn) {
      btn.classList.toggle("active", alwaysOnTop);
      btn.textContent = alwaysOnTop ? "고정 켜짐" : "꺼짐";
    }
    try {
      await fetch("/api/window", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({always_on_top: alwaysOnTop})
      });
    } catch (e) {}
  }

  function escapeHtml(str) {
    return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function showInfoModal(title, bodyHtml) {
    document.getElementById("infoModalTitle").textContent = title;
    document.getElementById("infoModalBody").innerHTML = bodyHtml;
    document.getElementById("infoModalBackdrop").classList.add("show");
  }

  function closeInfoModal(e) {
    if (e && e.target && e.target.id !== "infoModalBackdrop") return;
    document.getElementById("infoModalBackdrop").classList.remove("show");
  }

  function openBoxModelsModal(providerId, boxId, e) {
    if (e) e.stopPropagation();
    if (!lastData || !lastData.providers) return;
    const p = lastData.providers.find(x => x.id === providerId);
    if (!p) return;
    const box = (p.boxes || []).find(b => b.id === boxId);
    if (!box) return;
    let items = Array.isArray(box.models) && box.models.length ? box.models : [];
    if (!items.length) {
      const raw = (box.subtitle || "").trim();
      items = raw ? raw.split(/[,·]+/).map(s => s.trim()).filter(Boolean) : [(box.title || "모델 정보 없음")];
    }
    let html = items.map(m => `<div class="info-modal-item">• ${escapeHtml(m)}</div>`).join("");
    if (box.note) html += `<div class="info-modal-note">${escapeHtml(box.note)}</div>`;
    showInfoModal(`${box.title} — 사용 가능 모델`, html);
  }

  function openProviderInfoModal(providerId, e) {
    if (e) e.stopPropagation();
    if (!lastData || !lastData.providers) return;
    const p = lastData.providers.find(x => x.id === providerId);
    if (!p) return;
    const plan = p.plan || p.badge || "연동됨";
    const account = p.account || "연동된 계정 정보 없음";
    const resetTxt = p.reset_text || "실시간 연동";
    let html = `
      <div class="info-modal-row"><span class="info-modal-label">로그인 계정</span><span class="info-modal-val">${escapeHtml(account)}</span></div>
      <div class="info-modal-row"><span class="info-modal-label">플랜</span><span class="info-modal-val">${escapeHtml(plan)}</span></div>
      <div class="info-modal-row"><span class="info-modal-label">실행 상태</span><span class="info-modal-val" style="color:${p.running ? 'var(--ok)' : 'var(--text-3)'}">${p.running ? '● 실행 중' : '미실행'}</span></div>
      <div class="info-modal-row"><span class="info-modal-label">갱신 / 리셋</span><span class="info-modal-val">${escapeHtml(resetTxt)}</span></div>
    `;
    if (p.note) html += `<div class="info-modal-note">${escapeHtml(p.note)}</div>`;
    showInfoModal(`${p.name} 계정 정보`, html);
  }

  const GLOBAL_REFRESH_SVG = '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>';
  let globalCooldownEnd = 0;
  let providerCooldownEnd = {};
  let cooldownTickTimer = null;

  function applyCooldownUI() {
    const now = Date.now();
    let anyActive = false;

    const gBtn = document.getElementById("btnGlobalRefresh");
    const gcBtn = document.getElementById("btnGlobalRefreshCompact");
    const remMsG = globalCooldownEnd - now;
    if (remMsG > 0) {
      anyActive = true;
      const sec = Math.ceil(remMsG / 1000);
      if (gBtn) { gBtn.disabled = true; gBtn.textContent = `${sec}s`; }
      if (gcBtn) { gcBtn.disabled = true; gcBtn.textContent = `${sec}`; }
    } else {
      if (gBtn) { gBtn.disabled = false; gBtn.innerHTML = `${GLOBAL_REFRESH_SVG}<span>새로고침</span>`; }
      if (gcBtn) { gcBtn.disabled = false; gcBtn.innerHTML = GLOBAL_REFRESH_SVG; }
    }

    document.querySelectorAll(".provider-refresh-btn[data-refresh-provider]").forEach(btn => {
      const pid = btn.getAttribute("data-refresh-provider");
      const remMs = (providerCooldownEnd[pid] || 0) - now;
      if (remMs > 0) {
        anyActive = true;
        btn.disabled = true;
        btn.textContent = `${Math.ceil(remMs / 1000)}`;
      } else {
        btn.disabled = false;
        btn.textContent = "↻";
      }
    });

    if (!anyActive && cooldownTickTimer) {
      clearInterval(cooldownTickTimer);
      cooldownTickTimer = null;
    }
  }

  function ensureCooldownTick() {
    applyCooldownUI();
    if (!cooldownTickTimer) cooldownTickTimer = setInterval(applyCooldownUI, 200);
  }

  async function manualGlobalRefresh() {
    if (Date.now() < globalCooldownEnd) return;
    globalCooldownEnd = Date.now() + 5000;
    ensureCooldownTick();
    await refreshNow(true);
  }

  async function refreshProvider(providerId, e) {
    if (e) e.stopPropagation();
    if (Date.now() < (providerCooldownEnd[providerId] || 0)) return;
    providerCooldownEnd[providerId] = Date.now() + 5000;
    ensureCooldownTick();
    await refreshNow(true, providerId);
  }

  window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeInfoModal(); });

  let updatePollTimer = null;

  async function checkForUpdates(manual = false) {
    try {
      const res = await fetch(`/api/update/check${manual ? "?force=1" : ""}`);
      const info = await res.json();
      const banner = document.getElementById("updateBanner");
      const textEl = document.getElementById("updateBannerText");
      const btn = document.getElementById("updateApplyBtn");
      if (info.update_available) {
        if (textEl) textEl.textContent = `새 버전 v${info.latest_version} 출시`;
        if (btn) {
          btn.disabled = false;
          btn.textContent = info.can_auto_update ? "자동 업데이트" : "다운로드";
        }
        if (banner) banner.classList.add("show");
      } else if (manual) {
        const up = document.getElementById("updatedAt");
        if (up) up.textContent = `최신 v${info.current_version}`;
      }
    } catch (e) {}
  }

  function dismissUpdateBanner() {
    document.getElementById("updateBanner")?.classList.remove("show");
  }

  async function triggerUpdate() {
    const btn = document.getElementById("updateApplyBtn");
    const textEl = document.getElementById("updateBannerText");
    if (btn) btn.disabled = true;
    try {
      await fetch("/api/update/start", {method: "POST"});
      if (updatePollTimer) clearInterval(updatePollTimer);
      updatePollTimer = setInterval(async () => {
        try {
          const r = await fetch("/api/update/status");
          const st = await r.json();
          if (textEl && st.message) textEl.textContent = st.message;
          if (st.state === "error" || st.state === "done") {
            clearInterval(updatePollTimer);
            updatePollTimer = null;
            if (btn) btn.disabled = false;
          }
        } catch (e) {
          clearInterval(updatePollTimer);
          updatePollTimer = null;
        }
      }, 350);
    } catch (e) {
      if (btn) btn.disabled = false;
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    applyTheme(themePref);
    updateModeHeaderUI();
    setTimeout(() => refreshNow(false), 120);
    setTimeout(() => checkForUpdates(false), 2000);
    setInterval(() => refreshNow(false), 15000);
  });
</script>
</body>
</html>"""


def _close_all_popup_procs():
    """Closes any temporary floating Chrome login popup windows and callback tabs."""
    procs = OAUTH_STATE.get("popup_procs", [])
    OAUTH_STATE["popup_procs"] = []
    for proc, tmp_dir in procs:
        try:
            proc.terminate()
            proc.wait(timeout=1.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if platform.system() == "Darwin":
        script = """
        tell application "Google Chrome"
            if it is running then
                repeat with w in windows
                    repeat with t in tabs of w
                        set u to URL of t
                        if u contains "/oauth/antigravity/callback" or u contains "localhost:1455/auth/callback" then
                            close t
                        end if
                    end repeat
                end repeat
            end if
        end tell
        """
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=2.0)
        except Exception:
            pass


def _open_floating_chrome_popup(url: str, isolated_closeable: bool = True):
    sys_name = platform.system()

    # 1. If Google Chrome is installed, open directly in the user's normal full-sized Chrome window
    #    using their existing logged-in Chrome profile (so they can just click their account immediately).
    chrome_candidates: List[str] = []
    if sys_name == "Darwin":
        chrome_candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif sys_name == "Windows":
        chrome_candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]

    for cbin in chrome_candidates:
        if os.path.exists(cbin):
            try:
                if sys_name == "Darwin":
                    subprocess.Popen(
                        ["open", "-a", "Google Chrome", url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.Popen(
                        [cbin, url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return
            except Exception:
                pass

    # 2. Fallback when Chrome is NOT installed: open small floating login window (Edge / Brave / WebView)
    fallback_binaries: List[str] = []
    if sys_name == "Darwin":
        fallback_binaries = [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif sys_name == "Windows":
        fallback_binaries = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]

    for b in fallback_binaries:
        if os.path.exists(b):
            try:
                if isolated_closeable:
                    tmp_dir = tempfile.mkdtemp(prefix="nooptoken_login_")
                    proc = subprocess.Popen(
                        [
                            b,
                            f"--app={url}",
                            f"--user-data-dir={tmp_dir}",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--window-size=500,700",
                            "--window-position=420,80",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    OAUTH_STATE["popup_procs"].append((proc, tmp_dir))
                else:
                    subprocess.Popen(
                        [b, f"--app={url}", "--window-size=500,700", "--window-position=420,80"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return
            except Exception:
                pass

    webbrowser.open(url)


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _build_antigravity_oauth_url(port: int) -> str:
    verifier, challenge = _pkce_pair()
    OAUTH_STATE["agy_verifier"] = verifier
    redirect_uri = f"http://127.0.0.1:{port}/oauth/antigravity/callback"
    cid, _ = get_agy_oauth_client()
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(AGY_SCOPES),
        "access_type": "offline",
        "prompt": "select_account consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _build_claude_oauth_url() -> str:
    verifier, challenge = _pkce_pair()
    state = secrets.token_hex(16)
    OAUTH_STATE["claude_verifier"] = verifier
    OAUTH_STATE["claude_state"] = state
    params = {
        "code": "true",
        "client_id": CLAUDE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": "https://console.anthropic.com/oauth/code/callback",
        "scope": CLAUDE_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return "https://claude.ai/oauth/authorize?" + urllib.parse.urlencode(params)


def _build_codex_oauth_url() -> str:
    verifier, challenge = _pkce_pair()
    state = secrets.token_hex(16)
    OAUTH_STATE["codex_verifier"] = verifier
    OAUTH_STATE["codex_state"] = state
    params = {
        "client_id": CODEX_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": "http://localhost:1455/auth/callback",
        "scope": CODEX_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "codex_cli_simplified_flow": "true",
    }
    return "https://auth.openai.com/oauth/authorize?" + urllib.parse.urlencode(params)


def _exchange_claude_code(raw_code: str) -> bool:
    parts = raw_code.strip().split("#")
    code = parts[0]
    state = parts[1] if len(parts) > 1 else OAUTH_STATE.get("claude_state", "")
    try:
        r = requests.post(
            "https://console.anthropic.com/v1/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": CLAUDE_CLIENT_ID,
                "code": code,
                "redirect_uri": "https://console.anthropic.com/oauth/code/callback",
                "code_verifier": OAUTH_STATE.get("claude_verifier", ""),
                "state": state,
            },
            headers={"Content-Type": "application/json"},
            timeout=5.0,
        )
        if r.status_code == 200:
            td = r.json()
            acc = td.get("access_token", "")
            ref = td.get("refresh_token", "")
            exp = int(time.time() + int(td.get("expires_in", 3600)))
            if acc:
                save_config({
                    "auth": {
                        "claude": {
                            "access_token": acc,
                            "refresh_token": ref,
                            "expires_at": exp,
                        }
                    }
                })
                invalidate_provider_cache("claude")
                _close_all_popup_procs()
                return True
    except Exception:
        pass
    return False


class CodexCallbackHandler(BaseHTTPRequestHandler):
    timeout = 10

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/auth/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            code = (qs.get("code") or [""])[0]
            if code:
                try:
                    r = requests.post(
                        "https://auth.openai.com/oauth/token",
                        json={
                            "client_id": CODEX_CLIENT_ID,
                            "grant_type": "authorization_code",
                            "code": code,
                            "redirect_uri": "http://localhost:1455/auth/callback",
                            "code_verifier": OAUTH_STATE.get("codex_verifier", ""),
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=5.0,
                    )
                    if r.status_code == 200:
                        td = r.json()
                        acc = td.get("access_token", "")
                        ref = td.get("refresh_token", "")
                        exp = int(time.time() + int(td.get("expires_in", 3600)))
                        if acc:
                            save_config({
                                "auth": {
                                    "codex": {
                                        "access_token": acc,
                                        "refresh_token": ref,
                                        "expires_at": exp,
                                    }
                                }
                            })
                            invalidate_provider_cache("codex")
                            if GLOBAL_API.window:
                                try:
                                    GLOBAL_API.window.evaluate_js("refreshNow(true)")
                                except Exception:
                                    pass
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SUCCESS_CLOSE_HTML.encode("utf-8"))
            threading.Timer(0.4, _close_all_popup_procs).start()


def _get_runtime_dir() -> Path:
    if platform.system() == "Windows":
        local_app = os.environ.get("LOCALAPPDATA", "")
        base = Path(local_app) if local_app else (Path.home() / "AppData/Local")
        d = base / "NoopToken"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path.home()


def _setup_logging(cli_mode: bool = False) -> Path:
    rt_dir = _get_runtime_dir()
    log_path = rt_dir / ("widget.log" if platform.system() == "Windows" else ".nooptoken.log")
    try:
        if not cli_mode:
            log_file = open(log_path, "a", encoding="utf-8", buffering=1)
            if sys.stdout is None or platform.system() == "Windows":
                sys.stdout = log_file
            if sys.stderr is None or platform.system() == "Windows":
                sys.stderr = log_file
        logging.basicConfig(
            filename=str(log_path),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            encoding="utf-8",
        )
    except Exception:
        pass
    return log_path


def _cleanup_previous_instance() -> None:
    """Terminates any previous stuck/zombie instance of TokenChecker before starting."""
    rt_dir = _get_runtime_dir()
    pid_path = rt_dir / ("widget.pid" if platform.system() == "Windows" else ".nooptoken.pid")
    my_pid = os.getpid()

    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text(encoding="utf-8").strip())
            if old_pid > 0 and old_pid != my_pid:
                logging.info(f"Cleaning up previous instance PID {old_pid}")
                if platform.system() == "Windows":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(old_pid), "/T"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=3.0,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                    )
                else:
                    os.kill(old_pid, signal.SIGTERM)
                time.sleep(0.25)
        except Exception:
            pass

    # On Windows, also clean up any zombie pythonw.exe holding port 17890
    if platform.system() == "Windows":
        try:
            ps_kill = (
                f"Get-NetTCPConnection -LocalPort 17890 -ErrorAction SilentlyContinue | "
                f" Select-Object -ExpandProperty OwningProcess -Unique | "
                f" Where-Object {{ $_ -gt 0 -and $_ -ne {my_pid} }} | "
                f" ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"
            )
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_kill],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
        except Exception:
            pass

    try:
        pid_path.write_text(str(my_pid), encoding="utf-8")
    except Exception:
        pass


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, allow_reuse_address=True sets SO_REUSEADDR which permits port hijacking by zombie processes.
    allow_reuse_address = platform.system() != "Windows"

    def server_bind(self):
        if platform.system() == "Windows" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        super().server_bind()


def _ensure_codex_callback_server():
    try:
        server = ExclusiveThreadingHTTPServer(("127.0.0.1", 1455), CodexCallbackHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
    except OSError:
        pass


class WidgetApi:
    def __init__(self):
        self.window = None

    def get_quotas(self, force: bool = False) -> Dict[str, Any]:
        return fetch_all_quotas(force=bool(force))

    def save_order(self, card_order: List[str], box_order: Dict[str, List[str]]) -> bool:
        save_config({"card_order": card_order, "box_order": box_order})
        return True

    def set_always_on_top(self, flag: bool) -> bool:
        save_config({"always_on_top": bool(flag)})
        if self.window:
            try:
                self.window.on_top = bool(flag)
            except Exception:
                pass
        return True

    def set_compact(self, compact: bool) -> bool:
        save_config({"compact_mode": bool(compact)})
        if self.window:
            try:
                if compact:
                    self.window.resize(420, 560)
                else:
                    self.window.resize(920, 660)
            except Exception:
                pass
        return True

    def logout_provider(self, provider_id: str) -> Dict[str, Any]:
        return clear_provider_auth(provider_id)

    def open_login_window(self, provider_id: str) -> bool:
        port = OAUTH_STATE["server_port"]
        if provider_id == "antigravity":
            url = _build_antigravity_oauth_url(port)
            _open_floating_chrome_popup(url, isolated_closeable=True)
            return True
        elif provider_id == "claude":
            url = _build_claude_oauth_url()
            _open_floating_chrome_popup(url, isolated_closeable=False)
            return True
        elif provider_id == "codex":
            _ensure_codex_callback_server()
            url = _build_codex_oauth_url()
            _open_floating_chrome_popup(url, isolated_closeable=True)
            return True
        elif provider_id == "cursor":
            _open_floating_chrome_popup("https://www.cursor.com/settings", isolated_closeable=False)
            return True
        return False

    def submit_auth_code(self, provider_id: str, code_or_token: str) -> bool:
        val = code_or_token.strip()
        if not val:
            return False
        if provider_id == "claude":
            if val.startswith("sk-ant-sid"):
                save_config({"auth": {"claude": {"session_key": val}}})
                invalidate_provider_cache("claude")
                return True
            return _exchange_claude_code(val)
        elif provider_id == "cursor":
            save_config({"auth": {"cursor": {"session_token": val}}})
            invalidate_provider_cache("cursor")
            return True
        return False


GLOBAL_API = WidgetApi()


class LocalHTTPHandler(BaseHTTPRequestHandler):
    timeout = 10

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        if parsed.path == "/api/update/check":
            qs = urllib.parse.parse_qs(parsed.query)
            force = bool(qs.get("force"))
            data = json.dumps(check_for_update(force=force), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/update/status":
            data = json.dumps(get_update_status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/quotas":
            qs = urllib.parse.parse_qs(parsed.query)
            force = bool(qs.get("force"))
            provider = (qs.get("provider") or [""])[0]
            data = json.dumps(fetch_all_quotas(force=force, force_provider=provider), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/oauth/antigravity/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            code = (qs.get("code") or [""])[0]
            port = OAUTH_STATE["server_port"]
            redirect_uri = f"http://127.0.0.1:{port}/oauth/antigravity/callback"
            if code:
                try:
                    cid, csec = get_agy_oauth_client()
                    r = requests.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": cid,
                            "client_secret": csec,
                            "code": code,
                            "code_verifier": OAUTH_STATE.get("agy_verifier", ""),
                            "grant_type": "authorization_code",
                            "redirect_uri": redirect_uri,
                        },
                        timeout=5.0,
                    )
                    if r.status_code == 200:
                        td = r.json()
                        acc = td.get("access_token", "")
                        ref = td.get("refresh_token", "")
                        exp = int(time.time() + int(td.get("expires_in", 3600)))
                        email = ""
                        try:
                            ui = requests.get(
                                "https://www.googleapis.com/oauth2/v2/userinfo",
                                headers={"Authorization": f"Bearer {acc}"},
                                timeout=3.0,
                            ).json()
                            email = ui.get("email", "")
                        except Exception:
                            pass
                        save_config({
                            "auth": {
                                "antigravity": {
                                    "access_token": acc,
                                    "refresh_token": ref,
                                    "expires_at": exp,
                                    "email": email,
                                }
                            }
                        })
                        invalidate_provider_cache("antigravity")
                        if GLOBAL_API.window:
                            try:
                                GLOBAL_API.window.evaluate_js("refreshNow(true)")
                            except Exception:
                                pass
                except Exception:
                    pass

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SUCCESS_CLOSE_HTML.encode("utf-8"))
            threading.Timer(0.3, _close_all_popup_procs).start()
            return

        if parsed.path == "/assets/icon.png":
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            icon_p = base / "assets" / "icon.png"
            if not icon_p.exists():
                icon_p = Path(__file__).resolve().parent / "assets" / "icon.png"
            if icon_p.exists():
                data = icon_p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "max-age=3600")
                self.end_headers()
                self.wfile.write(data)
                return

        body = UI_HTML.replace("__APP_VERSION__", APP_VERSION).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/update/start":
            data = json.dumps(start_update(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/api/notify":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            enabled = bool(payload.get("enabled", True))
            save_config({"notifications_enabled": enabled})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "enabled": enabled}).encode("utf-8"))
            return

        if self.path == "/api/save_order":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            GLOBAL_API.save_order(payload.get("card_order", []), payload.get("box_order", {}))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        if self.path.startswith("/api/login/"):
            provider_id = self.path.split("/api/login/")[1]
            GLOBAL_API.open_login_window(provider_id)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        if self.path == "/api/submit_code":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            ok = GLOBAL_API.submit_auth_code(payload.get("provider_id", ""), payload.get("code", ""))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok}).encode("utf-8"))
            return

        if self.path.startswith("/api/logout/"):
            provider_id = self.path.split("/api/logout/")[1]
            clear_provider_auth(provider_id)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        if self.path == "/api/theme":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            theme = "light" if payload.get("theme") == "light" else "dark"
            save_config({"theme": theme})
            if platform.system() == "Windows":
                try:
                    import ctypes
                    hwnd = ctypes.windll.user32.FindWindowW(None, APP_NAME)
                    if hwnd:
                        _apply_windows_window_style(hwnd, dark=(theme == "dark"))
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "theme": theme}).encode("utf-8"))
            return

        if self.path == "/api/window":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            if "compact" in payload:
                compact = bool(payload["compact"])
                save_config({"compact_mode": compact})
                if platform.system() == "Windows":
                    try:
                        import ctypes
                        from ctypes import wintypes
                        user32 = ctypes.windll.user32
                        hwnd = user32.FindWindowW(None, APP_NAME)
                        if hwnd:
                            scale = 1.0
                            try:
                                dpi = user32.GetDpiForWindow(hwnd)
                                if dpi and dpi > 0:
                                    scale = dpi / 96.0
                            except Exception:
                                pass
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            target_w = int((420 if compact else 920) * scale)
                            target_h = int((560 if compact else 660) * scale)
                            user32.SetWindowPos(hwnd, 0, 0, 0, target_w, target_h, 0x0002 | 0x0004 | 0x0010)
                    except Exception:
                        pass
                else:
                    GLOBAL_API.set_compact(compact)
            if "always_on_top" in payload:
                on_top = bool(payload["always_on_top"])
                save_config({"always_on_top": on_top})
                if platform.system() == "Windows":
                    try:
                        import ctypes
                        user32 = ctypes.windll.user32
                        hwnd = user32.FindWindowW(None, APP_NAME)
                        if hwnd:
                            z_order = -1 if on_top else -2
                            user32.SetWindowPos(hwnd, z_order, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
                    except Exception:
                        pass
                else:
                    GLOBAL_API.set_always_on_top(on_top)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return


def start_background_http_server(port: int = 17890) -> int:
    for p in range(port, port + 20):
        try:
            server = ExclusiveThreadingHTTPServer(("127.0.0.1", p), LocalHTTPHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            OAUTH_STATE["server_port"] = p
            logging.info(f"Local ThreadingHTTPServer bound exclusively on 127.0.0.1:{p}")
            return p
        except OSError as e:
            logging.warning(f"Port {p} busy ({e}), trying next...")
            continue
    return 0


def run_cli_summary():
    data = fetch_all_quotas(force=True)
    print(f"\n=== {APP_NAME} v{APP_VERSION} ({data['updated_at']}) ===")
    for p in data["providers"]:
        if not p.get("logged_in"):
            print(f"• {p['name']:16s} [미로그인] -> 위젯에서 '{p.get('login_label')}' 버튼을 눌러 로그인하세요.")
        else:
            rem_pct = float(p.get("remaining_pct", 0.0))
            used_pct = round(max(0.0, min(100.0, 100.0 - rem_pct)), 1)
            print(f"• {p['name']:16s} (최대 {used_pct:5.1f}% 사용 / 최저 {rem_pct:5.1f}% 남음 | {p['headline']})")
            for box in p.get("boxes", []):
                b_rem = float(box.get("remaining_pct", 0.0))
                b_used = round(max(0.0, min(100.0, 100.0 - b_rem)), 1)
                print(f"   ┌─ [{box['title']}] ({box.get('subtitle', '')}) - {b_used:.1f}% 사용 ({b_rem:.1f}% 남음)")
                for bar in box.get("bars", []):
                    bar_rem = float(bar.get("remaining_pct", 0.0))
                    bar_used = round(max(0.0, min(100.0, 100.0 - bar_rem)), 1)
                    print(f"   │   • {bar['name']:18s}: {bar_used:5.1f}% 사용 / {bar_rem:5.1f}% 남음 ({bar.get('reset_text', '')})")
    print()


def _apply_windows_window_style(hwnd: int, dark: bool = True) -> None:
    """Apply native Windows 10/11 dark/light title bar, caption tint, and rounded corners."""
    if platform.system() != "Windows" or not hwnd:
        return
    try:
        import ctypes
        dwmapi = ctypes.windll.dwmapi
        dark_val = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE (20 on Win10 2004+/Win11, 19 on older Win10)
        res = dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
        if res != 0:
            dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
        # DWMWA_WINDOW_CORNER_PREFERENCE (33): DWMWCP_ROUND (2) on Windows 11
        corner_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
        # DWMWA_CAPTION_COLOR (35): COLORREF 0x00BBGGRR matching UI --bg (#0b0d15 / #f5f6fa)
        caption_bgr = ctypes.c_int(0x00150D0B if dark else 0x00FAF6F5)
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_bgr), ctypes.sizeof(caption_bgr))
        # DWMWA_TEXT_COLOR (36): COLORREF 0x00BBGGRR matching UI --text (#f1f5f9 / #0f172a)
        text_bgr = ctypes.c_int(0x00F9F5F1 if dark else 0x002A170F)
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_bgr), ctypes.sizeof(text_bgr))
    except Exception:
        pass


def _resolve_asset_path(filename: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    p = base / "assets" / filename
    if p.exists():
        return p
    return Path(__file__).resolve().parent / "assets" / filename


def _patch_pywebview_winforms_deadlock() -> None:
    """
    Fixes the pywebview 6.x + pythonnet 3.x GIL / WinForms STA UI thread deadlock on Windows:
    1. Replaces `while thread.IsAlive: thread.Join(500)` (.NET CLR blocking call that starves the GIL)
       with a pure Python `threading.Event.wait(0.5)` (`Py_BEGIN_ALLOW_THREADS` in C).
    2. Removes the 500ms WinForms.Timer (`timer_tick`) and WebView2 `WebResourceRequested` /
       `WebResourceResponseReceived` / `inject_pywebview` background thread `Control.Invoke` calls
       so the WinForms UI thread and Python GIL never contend or deadlock.
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        import webview.platforms.winforms as wf
        import webview.platforms.edgechromium as ec
        import webview.util as wutil

        def _noop_inject_pywebview(platform_name, window):
            window.events.before_load.set()
            window.events._pywebviewready.set()
            window.events.loaded.set()

        wutil.inject_pywebview = _noop_inject_pywebview
        ec.inject_pywebview = _noop_inject_pywebview

        def _safe_on_webview_ready(self, sender, args):
            try:
                if not args.IsSuccess:
                    logging.error(f"WebView2 initialization failed: {args.InitializationException}")
                    return
                settings = sender.CoreWebView2.Settings
                settings.AreDefaultScriptDialogsEnabled = True
                settings.IsBuiltInErrorPageEnabled = True
                settings.IsScriptEnabled = True
                settings.IsWebMessageEnabled = False
                settings.IsStatusBarEnabled = False
                settings.IsSwipeNavigationEnabled = False
                settings.IsZoomControlEnabled = True
                if self.pywebview_window.real_url:
                    logging.info(f"[GUI] WebView2 ready, navigating to {self.pywebview_window.real_url}")
                    self.load_url(self.pywebview_window.real_url)
                elif self.pywebview_window.html:
                    self.load_html(self.pywebview_window.html, "")
            except Exception as ex:
                logging.error(f"Error in _safe_on_webview_ready: {ex}")

        def _safe_on_navigation_completed(self, sender, _):
            self.pywebview_window.events.before_load.set()
            self.pywebview_window.events._pywebviewready.set()
            self.pywebview_window.events.loaded.set()
            logging.info("[GUI] WebView2 NavigationCompleted")

        ec.EdgeChrome.on_webview_ready = _safe_on_webview_ready
        ec.EdgeChrome.on_navigation_completed = _safe_on_navigation_completed

        gui_done_event = threading.Event()

        def _safe_create_window(window):
            def create():
                try:
                    logging.info("[GUI] STA thread create() entered")
                    browser = wf.BrowserView.BrowserForm(window, wf.cache_dir)
                    try:
                        ico_path = _resolve_asset_path("icon.ico")
                        if ico_path.exists():
                            from System.Drawing import Icon as DotNetIcon
                            browser.Icon = DotNetIcon(str(ico_path))
                    except Exception as icon_ex:
                        logging.warning(f"[GUI] Could not set WinForms window icon: {icon_ex}")
                    wf.BrowserView.instances[window.uid] = browser
                    window.events.before_show.set()
                    try:
                        is_dark = load_config().get("theme", "light") == "dark"
                        _apply_windows_window_style(int(browser.Handle.ToInt64()), dark=is_dark)
                    except Exception:
                        pass
                    browser.Show()
                    browser.Activate()
                    try:
                        is_dark = load_config().get("theme", "light") == "dark"
                        _apply_windows_window_style(int(browser.Handle.ToInt64()), dark=is_dark)
                    except Exception:
                        pass
                    wf._main_window_created.set()
                    logging.info("[GUI] BrowserForm shown, entering WinForms Application.Run()")
                    if window.uid == "master":
                        wf.WinForms.Application.Run(browser)
                except Exception as ex:
                    logging.error(f"[GUI] Exception in STA create(): {ex}\n{traceback.format_exc()}")
                finally:
                    gui_done_event.set()
                    os._exit(0)

            if window.uid == "master":
                if wf.is_chromium:
                    wf.init_storage()
                try:
                    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (-4) for sharp rendering on 125%/150% displays
                    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                except Exception:
                    try:
                        if sys.getwindowsversion().major >= 6:
                            ctypes.windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass
                thread = wf.Thread(wf.ThreadStart(create))
                thread.SetApartmentState(wf.ApartmentState.STA)
                thread.Start()
                logging.info("[GUI] STA thread started; main thread releasing GIL via Event.wait()")
                while not gui_done_event.wait(0.5):
                    pass

        wf.create_window = _safe_create_window
        logging.info("Applied Windows pywebview WinForms/GIL deadlock-free patch.")
    except Exception as e:
        logging.error(f"Failed to patch pywebview winforms: {e}\n{traceback.format_exc()}")


def _run_server_worker(port: int, parent_pid: int) -> None:
    """Runs the HTTP server in a dedicated process completely isolated from the GUI/WinForms GIL."""
    _setup_logging(cli_mode=False)
    OAUTH_STATE["server_port"] = port
    logging.info(f"[ServerWorker] Starting isolated HTTP server on 127.0.0.1:{port} (parent_pid={parent_pid})")
    _ensure_codex_callback_server()
    server = ExclusiveThreadingHTTPServer(("127.0.0.1", port), LocalHTTPHandler)

    def _watch_parent():
        while True:
            time.sleep(1.5)
            if parent_pid > 0:
                if platform.system() == "Windows":
                    import ctypes
                    SYNCHRONIZE = 0x00100000
                    STILL_ACTIVE = 259
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, parent_pid)
                    if not h:
                        logging.info("[ServerWorker] Parent GUI process exited; shutting down server worker.")
                        os._exit(0)
                    exit_code = ctypes.c_ulong(0)
                    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                    ctypes.windll.kernel32.CloseHandle(h)
                    if exit_code.value != STILL_ACTIVE:
                        logging.info("[ServerWorker] Parent GUI process terminated; shutting down server worker.")
                        os._exit(0)
                else:
                    try:
                        os.kill(parent_pid, 0)
                    except OSError:
                        os._exit(0)

    threading.Thread(target=_watch_parent, daemon=True).start()
    server.serve_forever()


def _find_free_port(start_port: int = 17890) -> int:
    for p in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if platform.system() == "Windows" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                except OSError:
                    pass
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start_port


def _build_server_worker_cmd(port: int, parent_pid: int) -> List[str]:
    """Build command arguments to spawn the isolated HTTP server worker for frozen or source runs."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--server-worker", str(port), str(parent_pid)]
    return [sys.executable, os.path.abspath(__file__), "--server-worker", str(port), str(parent_pid)]


def main():
    parser = argparse.ArgumentParser(description="AI Agent Official Quota Floating Widget")
    parser.add_argument("--cli", action="store_true", help="터미널에서 상태 확인")
    parser.add_argument("--server-worker", nargs=2, metavar=("PORT", "PARENT_PID"), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.server_worker:
        _run_server_worker(int(args.server_worker[0]), int(args.server_worker[1]))
        return

    log_path = _setup_logging(cli_mode=bool(args.cli))

    if args.cli:
        run_cli_summary()
        return

    logging.info("==========================================")
    logging.info(f"Starting {APP_NAME} ({APP_EN_NAME} v{APP_VERSION}, PID={os.getpid()}, OS={platform.system()})")
    _cleanup_previous_instance()

    if platform.system() == "Windows":
        # On Windows, run the HTTP server in a separate child process so the GUI process has ZERO background threads
        # and ZERO GIL contention with pythonnet / WinForms.
        port = _find_free_port(17890)
        OAUTH_STATE["server_port"] = port
        server_proc = subprocess.Popen(
            _build_server_worker_cmd(port, os.getpid()),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            close_fds=True,
        )
        logging.info(f"Spawned isolated server worker process PID={server_proc.pid} on port {port}")
        url = f"http://127.0.0.1:{port}"
        worker_healthy = False
        for _ in range(30):
            try:
                r = requests.get(f"{url}/api/health", timeout=0.3)
                if r.status_code == 200:
                    logging.info(f"Server worker healthy at {url}")
                    worker_healthy = True
                    break
            except Exception:
                time.sleep(0.1)
        if not worker_healthy:
            err_msg = f"Server worker failed to respond on {url} after 30 attempts."
            logging.error(err_msg)
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"로컬 서버 워커가 응답하지 않아 {APP_NAME}를 시작할 수 없습니다.\n({url})",
                    APP_NAME,
                    0x10,
                )
            except Exception:
                pass
            return
    else:
        port = start_background_http_server(17890)
        _ensure_codex_callback_server()
        url = f"http://127.0.0.1:{port}"

    try:
        import webview

        if platform.system() == "Windows":
            _patch_pywebview_winforms_deadlock()

        cfg = load_config()
        init_bg = "#0b0d15" if cfg.get("theme") == "dark" else "#f5f6fa"
        window = webview.create_window(
            title=APP_NAME,
            url=url,
            width=920,
            height=660,
            x=80,
            y=80,
            resizable=True,
            on_top=bool(cfg.get("always_on_top", False)),
            background_color=init_bg,
        )
        GLOBAL_API.window = window

        def _on_closed():
            logging.info("Widget window closed by user; terminating process cleanly.")
            os._exit(0)

        try:
            window.events.closed += _on_closed
        except Exception:
            pass

        logging.info(f"{APP_NAME} v{APP_VERSION} window created at {url} (log: {log_path})")
        print(f"{APP_NAME} v{APP_VERSION} started at {url}")
        webview.start(debug=False)
        os._exit(0)
    except Exception as e:
        logging.error(f"WebView startup error: {e}\n{traceback.format_exc()}")
        print(f"Fallback to browser ({e}): {url}")
        webbrowser.open(url)
        threading.Event().wait()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
