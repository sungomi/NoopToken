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
<title>TokenChecker</title>
<style>
  :root {
    --bg: #080a0f;
    --bg-glow: rgba(56, 189, 248, 0.06);
    --card-bg: rgba(18, 23, 34, 0.88);
    --card-border: rgba(255, 255, 255, 0.075);
    --card-border-hover: rgba(255, 255, 255, 0.14);
    --box-bg: rgba(10, 13, 20, 0.68);
    --box-border: rgba(255, 255, 255, 0.055);
    --text: #f8fafc;
    --text-sub: #cbd5e1;
    --muted: #64748b;
    --accent: #38bdf8;
  }
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    user-select: none;
    -webkit-user-select: none;
  }
  body {
    background-color: var(--bg);
    background-image: radial-gradient(ellipse 90% 40% at 50% -10%, var(--bg-glow), transparent);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Pretendard", "Segoe UI", sans-serif;
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
    overflow-x: hidden;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    -webkit-font-smoothing: antialiased;
  }

  /* Custom Scrollbar */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 99px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.24); }

  /* Top Header */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 16px 10px 16px;
    background: rgba(8, 10, 15, 0.86);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    position: sticky;
    top: 0;
    z-index: 30;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    white-space: nowrap;
  }
  .title-area {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    font-size: 13.5px;
    letter-spacing: -0.02em;
    color: #f1f5f9;
    white-space: nowrap;
    flex-shrink: 0;
    word-break: keep-all;
  }
  .app-logo-badge {
    width: 21px;
    height: 21px;
    border-radius: 6px;
    background: linear-gradient(135deg, #06b6d4 0%, #10b981 50%, #6366f1 100%);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.35);
    flex-shrink: 0;
  }
  .app-logo-badge svg {
    width: 14px;
    height: 14px;
  }
  .version-pill {
    font-size: 9.5px;
    font-weight: 600;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.1);
    border: 1px solid rgba(56, 189, 248, 0.24);
    border-radius: 99px;
    padding: 1.5px 6px;
    cursor: pointer;
    transition: all 0.16s ease;
    letter-spacing: 0;
  }
  .version-pill:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.48);
  }
  .update-banner {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin: 8px 14px 0 14px;
    padding: 7px 10px;
    border-radius: 9px;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.14), rgba(56, 189, 248, 0.12));
    border: 1px solid rgba(16, 185, 129, 0.32);
    font-size: 11px;
    color: #e2e8f0;
  }
  .update-banner.show {
    display: flex;
  }
  .update-banner-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .update-apply-btn {
    background: linear-gradient(135deg, #10b981, #0ea5e9);
    color: #061018;
    border: none;
    border-radius: 6px;
    padding: 4px 9px;
    font-size: 10.5px;
    font-weight: 700;
    cursor: pointer;
  }
  .update-apply-btn:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .update-close-btn {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-size: 12px;
    cursor: pointer;
    padding: 2px 4px;
  }
  .live-indicator {
    position: relative;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.8);
    transition: background 0.25s ease;
    flex-shrink: 0;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .ctrl-btn {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #94a3b8;
    border-radius: 7px;
    height: 26px;
    padding: 0 7.5px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    transition: all 0.16s ease;
    white-space: nowrap;
    flex-shrink: 0;
    word-break: keep-all;
    line-height: 1;
  }
  .ctrl-btn:hover {
    color: #f8fafc;
    background: rgba(255, 255, 255, 0.09);
    border-color: rgba(255, 255, 255, 0.16);
  }
  .ctrl-btn:disabled {
    opacity: 0.65;
    cursor: default;
    color: #38bdf8;
    min-width: 28px;
  }
  .ctrl-btn.active {
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.4);
    background: rgba(56, 189, 248, 0.12);
  }
  .ctrl-btn svg {
    width: 12px;
    height: 12px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  /* Top 4-Pill Summary Bar */
  .mini-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 7px;
    padding: 10px 14px 4px 14px;
  }
  .mini-pill {
    background: linear-gradient(180deg, rgba(24, 30, 44, 0.78) 0%, rgba(15, 19, 29, 0.88) 100%);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    padding: 7px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    cursor: pointer;
    transition: all 0.16s ease;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }
  .mini-pill:hover {
    border-color: var(--card-border-hover);
    transform: translateY(-1px);
  }
  .mini-pill-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10.5px;
    color: #94a3b8;
    font-weight: 600;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }
  .mini-pill-val {
    font-size: 13px;
    font-weight: 800;
    letter-spacing: -0.02em;
    white-space: nowrap;
  }
  .mini-progress {
    height: 3.5px;
    background: rgba(255, 255, 255, 0.07);
    border-radius: 99px;
    overflow: hidden;
  }
  .mini-progress-fill {
    height: 100%;
    border-radius: 99px;
    transition: width 0.4s ease;
  }

  /* Main Account Cards List */
  .cards {
    padding: 6px 14px 14px 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    flex: 1;
  }
  body.compact .cards {
    display: none;
  }

  .card {
    background: linear-gradient(180deg, rgba(22, 28, 42, 0.86) 0%, rgba(14, 18, 28, 0.94) 100%);
    border: 1px solid var(--card-border);
    border-radius: 13px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    overflow: hidden;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.12s ease;
  }
  .card:hover {
    border-color: rgba(255, 255, 255, 0.12);
  }
  .card.dragging {
    opacity: 0.92;
    border-color: rgba(56, 189, 248, 0.65);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(56, 189, 248, 0.4);
    transform: scale(1.01);
    z-index: 25;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 11px 13px;
    cursor: grab;
    transition: background 0.15s ease;
  }
  .card-header:active {
    cursor: grabbing;
  }
  .card-header:hover {
    background: rgba(255, 255, 255, 0.025);
  }

  .provider-left {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .drag-grip {
    color: #475569;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 12px;
    height: 16px;
    flex-shrink: 0;
    transition: color 0.15s ease;
  }
  .card-header:hover .drag-grip,
  .box-header:hover .drag-grip {
    color: #94a3b8;
  }
  .drag-grip svg {
    width: 10px;
    height: 14px;
    fill: currentColor;
  }

  .brand-icon {
    width: 24px;
    height: 24px;
    border-radius: 7px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.2);
  }
  .brand-icon svg {
    width: 14px;
    height: 14px;
  }
  .brand-antigravity {
    background: linear-gradient(135deg, #4f46e5, #0ea5e9);
    color: #ffffff;
  }
  .brand-claude {
    background: linear-gradient(135deg, #d97757, #b45309);
    color: #ffffff;
  }
  .brand-cursor {
    background: linear-gradient(135deg, #0284c7, #22d3ee);
    color: #ffffff;
  }
  .brand-codex {
    background: linear-gradient(135deg, #059669, #10b981);
    color: #ffffff;
  }

  .provider-titles {
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }
  .provider-name {
    font-weight: 700;
    font-size: 13.5px;
    letter-spacing: -0.01em;
    color: #f8fafc;
    white-space: nowrap;
  }
  .badge {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 99px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: #94a3b8;
    font-weight: 600;
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .logout-btn {
    background: transparent;
    border: none;
    color: #475569;
    width: 20px;
    height: 20px;
    border-radius: 5px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .logout-btn:hover {
    color: #f87171;
    background: rgba(239, 68, 68, 0.14);
  }

  .card-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .pct-pill {
    display: flex;
    align-items: baseline;
    gap: 3px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .rem-pct {
    font-size: 15px;
    font-weight: 800;
    letter-spacing: -0.02em;
    white-space: nowrap;
  }
  .rem-label {
    font-size: 10px;
    color: var(--muted);
    font-weight: 600;
    white-space: nowrap;
  }
  .chevron-badge {
    width: 20px;
    height: 20px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    transition: transform 0.2s ease, background 0.15s ease;
  }
  .card-header:hover .chevron-badge {
    background: rgba(255, 255, 255, 0.09);
    color: #f8fafc;
  }
  .chevron-badge.folded {
    transform: rotate(-90deg);
  }

  .card-body {
    padding: 0 12px 12px 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.045);
  }
  .card-body.folded {
    display: none;
  }

  /* Inner Model Group Boxes (3 boxes in Antigravity, etc.) */
  .boxes-list {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .group-box {
    background: var(--box-bg);
    border: 1px solid var(--box-border);
    border-radius: 10px;
    overflow: hidden;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.12s ease;
  }
  .group-box:hover {
    border-color: rgba(255, 255, 255, 0.11);
  }
  .group-box.dragging {
    opacity: 0.94;
    border-color: rgba(56, 189, 248, 0.65);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.55);
    transform: scale(1.01);
  }

  .box-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8.5px 10px;
    cursor: grab;
    background: rgba(255, 255, 255, 0.015);
    transition: background 0.15s ease;
  }
  .box-header:active {
    cursor: grabbing;
  }
  .box-header:hover {
    background: rgba(255, 255, 255, 0.04);
  }
  .box-title-wrap {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }
  .box-title-btn {
    background: transparent;
    border: none;
    padding: 2px 5px;
    margin: -2px -5px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 12px;
    color: #f1f5f9;
    letter-spacing: -0.01em;
    white-space: nowrap;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: background 0.15s ease, color 0.15s ease;
  }
  .box-title-btn:hover {
    background: rgba(56, 189, 248, 0.14);
    color: #38bdf8;
  }
  .info-dot {
    font-size: 10.5px;
    color: #64748b;
    font-weight: 600;
  }
  .box-title-btn:hover .info-dot {
    color: #38bdf8;
  }
  .provider-info-btn {
    background: transparent;
    border: none;
    padding: 2px 5px;
    margin: -2px -5px;
    border-radius: 6px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    transition: background 0.15s ease;
  }
  .provider-info-btn:hover {
    background: rgba(56, 189, 248, 0.14);
  }
  .provider-info-btn:hover .provider-name {
    color: #38bdf8;
  }
  .provider-refresh-btn {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.09);
    background: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    font-size: 10.5px;
    line-height: 1;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
  }
  .provider-refresh-btn:hover {
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.45);
    background: rgba(56, 189, 248, 0.12);
  }
  .provider-refresh-btn:disabled {
    opacity: 0.7;
    cursor: default;
    color: #38bdf8;
    font-size: 9.5px;
    font-weight: 700;
  }

  /* Floating Info Modal */
  .info-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(4, 6, 10, 0.68);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    display: none;
    align-items: center;
    justify-content: center;
    padding: 18px;
    z-index: 100;
  }
  .info-modal-backdrop.show {
    display: flex;
  }
  .info-modal-card {
    width: 100%;
    max-width: 340px;
    background: rgba(17, 22, 33, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.65);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .info-modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .info-modal-title {
    font-size: 13.5px;
    font-weight: 700;
    color: #f8fafc;
  }
  .info-modal-close {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.09);
    color: #94a3b8;
    border-radius: 6px;
    width: 22px;
    height: 22px;
    cursor: pointer;
    font-size: 11px;
  }
  .info-modal-close:hover {
    color: #f8fafc;
    background: rgba(255, 255, 255, 0.12);
  }
  .info-modal-body {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 260px;
    overflow-y: auto;
  }
  .info-modal-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 11.5px;
  }
  .info-modal-label {
    color: #94a3b8;
    font-weight: 600;
    flex-shrink: 0;
  }
  .info-modal-val {
    color: #f1f5f9;
    font-weight: 600;
    text-align: right;
    word-break: break-all;
  }
  .info-modal-item {
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: #e2e8f0;
    font-size: 11.5px;
    font-weight: 500;
  }
  .info-modal-note {
    margin-top: 4px;
    padding: 8px 10px;
    border-radius: 8px;
    background: rgba(56, 189, 248, 0.08);
    border: 1px solid rgba(56, 189, 248, 0.2);
    color: #94a3b8;
    font-size: 10.5px;
    line-height: 1.45;
  }
  .box-right {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .box-pct-badge {
    font-size: 12px;
    font-weight: 800;
    padding: 1.5px 6px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.04);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .box-chevron {
    font-size: 9.5px;
    color: #64748b;
    transition: transform 0.18s ease;
    display: inline-block;
  }
  .box-chevron.folded {
    transform: rotate(-90deg);
  }

  .box-body {
    padding: 9px 11px 10px 11px;
    border-top: 1px solid rgba(255, 255, 255, 0.045);
    display: flex;
    flex-direction: column;
    gap: 9px;
  }
  .box-body.folded {
    display: none;
  }

  /* Progress Bars inside each Box (Weekly + 5h = 2 bars per box) */
  .bar-row {
    display: flex;
    flex-direction: column;
    gap: 4.5px;
  }
  .bar-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
  }
  .bar-name {
    color: #cbd5e1;
    font-weight: 600;
    font-size: 11px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .bar-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .bar-reset {
    font-size: 10px;
    color: #94a3b8;
    background: rgba(255, 255, 255, 0.045);
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 500;
    white-space: nowrap;
  }
  .bar-val {
    font-weight: 800;
    font-size: 11.5px;
    min-width: 38px;
    text-align: right;
    white-space: nowrap;
  }
  .bar-track {
    width: 100%;
    height: 6.5px;
    background: rgba(255, 255, 255, 0.065);
    border-radius: 99px;
    overflow: hidden;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.4);
  }
  .bar-fill {
    height: 100%;
    border-radius: 99px;
    transition: width 0.45s cubic-bezier(0.22, 1, 0.36, 1);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }

  /* Unauthenticated Login Button Card */
  .login-box {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .login-btn {
    width: 100%;
    padding: 9px 12px;
    border-radius: 9px;
    border: 1px solid rgba(56, 189, 248, 0.35);
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.16), rgba(99, 102, 241, 0.14));
    color: #f0f9ff;
    font-weight: 700;
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    transition: all 0.16s ease;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.12);
  }
  .login-btn:hover {
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.28), rgba(99, 102, 241, 0.24));
    border-color: rgba(56, 189, 248, 0.65);
    transform: translateY(-1px);
  }
  .login-hint {
    font-size: 10.5px;
    color: #64748b;
    line-height: 1.4;
  }

  .paste-box {
    display: none;
    margin-top: 4px;
    gap: 6px;
  }
  .paste-box.show {
    display: flex;
  }
  .paste-input {
    flex: 1;
    background: #07090e;
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: var(--text);
    border-radius: 7px;
    padding: 6px 9px;
    font-size: 11px;
    user-select: text;
    -webkit-user-select: text;
    outline: none;
  }
  .paste-input:focus {
    border-color: var(--accent);
  }
  .paste-submit {
    background: var(--accent);
    color: #080b11;
    border: none;
    border-radius: 7px;
    padding: 6px 11px;
    font-weight: 700;
    font-size: 11px;
    cursor: pointer;
  }

  .footer {
    padding: 7px 14px 9px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10px;
    color: #64748b;
    border-top: 1px solid rgba(255,255,255,0.04);
    background: rgba(8, 10, 15, 0.6);
  }
</style>
</head>
<body>

  <div class="header pywebview-drag-region">
    <div class="title-area">
      <span class="app-logo-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9" stroke-opacity="0.45" />
          <path d="M8.5 12.2l2.3 2.3 4.8-5" />
        </svg>
      </span>
      <span class="live-indicator" id="pulseDot"></span>
      <span id="appTitleText">TokenChecker</span>
    </div>
    <div class="controls">
      <button class="ctrl-btn active" id="btnDisplayMode" onclick="toggleDisplayMode()" title="사용량(%) / 잔여량(%) 표시 기준 전환">사용량 기준</button>
      <button class="ctrl-btn" onclick="toggleAllBoxes()" title="모든 계정/박스 접기·펼치기">접기</button>
      <button class="ctrl-btn" id="btnCompact" onclick="toggleCompact()" title="상단 미니바 모드로 축소">미니바</button>
      <button class="ctrl-btn active" id="btnPin" onclick="togglePin()" title="항상 위에 고정">고정</button>
      <button class="ctrl-btn" id="btnGlobalRefresh" onclick="manualGlobalRefresh()" title="전체 강제 새로고침 (5초 쿨다운)">
        <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>
      </button>
    </div>
  </div>

  <div class="update-banner" id="updateBanner">
    <span id="updateBannerText">새 버전이 있습니다</span>
    <div class="update-banner-actions">
      <button class="update-apply-btn" id="updateApplyBtn" onclick="triggerUpdate()">업데이트</button>
      <button class="update-close-btn" onclick="dismissUpdateBanner()" title="닫기">✕</button>
    </div>
  </div>

  <div class="mini-bar" id="miniBar"></div>
  <div class="cards" id="cardsContainer"></div>

  <div class="footer">
    <span style="display:inline-flex;align-items:center;gap:6px;">
      <span class="version-pill" id="appVersionBadge" onclick="checkForUpdates(true)" title="클릭하여 업데이트 확인">v__APP_VERSION__</span>
      <span>드래그하여 순서 변경</span>
    </span>
    <span id="updatedAt">동기화 중...</span>
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
  let alwaysOnTop = true;
  let openPasteBoxes = {};
  let lastData = null;
  let isDragging = false;

  // Persist fold states, displayMode (default: "used"), and custom ordering
  let displayMode = localStorage.getItem("ai_quota_display_mode") || "used";
  let foldedCards = JSON.parse(localStorage.getItem("ai_quota_folded_cards") || "{}");
  let foldedBoxes = JSON.parse(localStorage.getItem("ai_quota_folded_boxes") || "{}");
  let cardOrder = JSON.parse(localStorage.getItem("ai_quota_card_order") || '["antigravity","claude","cursor","codex"]');
  let boxOrder = JSON.parse(localStorage.getItem("ai_quota_box_order") || "{}");

  function saveStateToLocal() {
    localStorage.setItem("ai_quota_display_mode", displayMode);
    localStorage.setItem("ai_quota_folded_cards", JSON.stringify(foldedCards));
    localStorage.setItem("ai_quota_folded_boxes", JSON.stringify(foldedBoxes));
    localStorage.setItem("ai_quota_card_order", JSON.stringify(cardOrder));
    localStorage.setItem("ai_quota_box_order", JSON.stringify(boxOrder));
  }

  function updateModeHeaderUI() {
    const btn = document.getElementById("btnDisplayMode");
    const titleEl = document.getElementById("appTitleText");
    if (titleEl) titleEl.textContent = "TokenChecker";
    if (displayMode === "used") {
      if (btn) {
        btn.textContent = "사용량 기준";
        btn.classList.add("active");
      }
    } else {
      if (btn) {
        btn.textContent = "잔여량 기준";
        btn.classList.remove("active");
      }
    }
  }

  function toggleDisplayMode() {
    displayMode = (displayMode === "used") ? "remaining" : "used";
    saveStateToLocal();
    updateModeHeaderUI();
    if (lastData) render(lastData);
  }

  function getDisplayMetric(remPct) {
    const r = Math.max(0, Math.min(100, Number(remPct) || 0));
    if (displayMode === "used") {
      const used = Math.round((100 - r) * 10) / 10;
      return {
        pct: used,
        width: used,
        tag: "사용",
        summaryTag: "사용",
      };
    } else {
      const rem = Math.round(r * 10) / 10;
      return {
        pct: rem,
        width: rem,
        tag: "남음",
        summaryTag: "남음",
      };
    }
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

  function getBrandIconSvg(id) {
    if (id === "antigravity") {
      return `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2L12 2Z"/></svg>`;
    }
    if (id === "claude") {
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6L5.6 18.4"/></svg>`;
    }
    if (id === "cursor") {
      return `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 3l16 7.5-7.2 2.3L10.5 20 4 3z"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 20 7 20 17 12 22 4 17 4 7 12 2"/><circle cx="12" cy="12" r="3"/></svg>`;
  }

  function getGripSvg() {
    return `<svg viewBox="0 0 10 14"><circle cx="2.5" cy="2.5" r="1.2"/><circle cx="7.5" cy="2.5" r="1.2"/><circle cx="2.5" cy="7" r="1.2"/><circle cx="7.5" cy="7" r="1.2"/><circle cx="2.5" cy="11.5" r="1.2"/><circle cx="7.5" cy="11.5" r="1.2"/></svg>`;
  }

  function getColor(remPct) {
    if (remPct >= 50) return "#10b981";
    if (remPct >= 20) return "#f59e0b";
    return "#ef4444";
  }

  function getGradient(remPct) {
    if (remPct >= 50) return "linear-gradient(90deg, #059669 0%, #10b981 60%, #34d399 100%)";
    if (remPct >= 20) return "linear-gradient(90deg, #d97706 0%, #f59e0b 60%, #fbbf24 100%)";
    return "linear-gradient(90deg, #e11d48 0%, #ef4444 60%, #f87171 100%)";
  }

  function shortName(id) {
    if (id === "antigravity") return "AGY";
    if (id === "claude") return "Claude";
    if (id === "cursor") return "Cursor";
    if (id === "codex") return "Codex";
    return id;
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

  function toggleAllBoxes() {
    if (!lastData || !lastData.providers) return;
    const anyUnfolded = lastData.providers.some(p => !foldedCards[p.id]);
    lastData.providers.forEach(p => {
      foldedCards[p.id] = anyUnfolded;
      (p.boxes || []).forEach(b => {
        foldedBoxes[b.id] = anyUnfolded;
      });
    });
    saveStateToLocal();
    render(lastData);
  }

  async function fetchData(force = false, providerId = "") {
    try {
      let qs = "";
      if (force) {
        qs = providerId ? `?force=1&provider=${encodeURIComponent(providerId)}` : "?force=1";
      }
      const r = await fetch("/api/quotas" + qs);
      return await r.json();
    } catch (e) {
      return null;
    }
  }

  let loginPollTimer = null;

  async function openLogin(providerId, event) {
    if (event) event.stopPropagation();
    if (providerId === "claude" || providerId === "cursor") {
      openPasteBoxes[providerId] = true;
      if (lastData) render(lastData);
    }
    try {
      await fetch("/api/login/" + providerId, { method: "POST" });
    } catch (e) {}
    if (loginPollTimer) clearInterval(loginPollTimer);
    let ticks = 0;
    loginPollTimer = setInterval(async () => {
      ticks++;
      await refreshNow(true);
      if (lastData && lastData.providers) {
        const p = lastData.providers.find(x => x.id === providerId);
        if (p && p.logged_in) {
          clearInterval(loginPollTimer);
          loginPollTimer = null;
        }
      }
      if (ticks > 40) {
        clearInterval(loginPollTimer);
        loginPollTimer = null;
      }
    }, 1500);
  }

  async function submitCodeOrToken(providerId, event) {
    if (event) event.stopPropagation();
    const el = document.getElementById("input_" + providerId);
    if (!el || !el.value.trim()) return;
    const val = el.value.trim();
    try {
      await fetch("/api/submit_code", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({provider_id: providerId, code: val})
      });
    } catch (e) {}
    openPasteBoxes[providerId] = false;
    await refreshNow(true);
  }

  async function logoutProvider(providerId, event) {
    if (event) event.stopPropagation();
    try {
      await fetch("/api/logout/" + providerId, { method: "POST" });
    } catch (e) {}
    await refreshNow(true);
  }

  function applyClientOrdering(providers) {
    const map = {};
    providers.forEach(p => { map[p.id] = p; });
    const orderedIds = cardOrder.filter(id => map[id]).concat(
      providers.map(p => p.id).filter(id => !cardOrder.includes(id))
    );
    cardOrder = orderedIds;

    return orderedIds.map(pid => {
      const p = Object.assign({}, map[pid]);
      if (p.boxes && p.boxes.length > 0) {
        const bOrder = boxOrder[pid] || [];
        const bMap = {};
        p.boxes.forEach(b => { bMap[b.id] = b; });
        const orderedBoxIds = bOrder.filter(bid => bMap[bid]).concat(
          p.boxes.map(b => b.id).filter(bid => !bOrder.includes(bid))
        );
        boxOrder[pid] = orderedBoxIds;
        p.boxes = orderedBoxIds.map(bid => bMap[bid]);
      }
      return p;
    });
  }

  function render(data) {
    if (!data || !data.providers || isDragging) return;
    lastData = data;
    document.getElementById("updatedAt").textContent = "갱신 " + data.updated_at;

    const savedInputs = {};
    ["claude", "cursor"].forEach(id => {
      const el = document.getElementById("input_" + id);
      if (el) savedInputs[id] = el.value;
    });

    const orderedProviders = applyClientOrdering(data.providers);

    // 1. Mini Bar (matches exact cardOrder)
    const miniBar = document.getElementById("miniBar");
    miniBar.innerHTML = orderedProviders.map(p => {
      if (!p.logged_in) {
        return `
          <div class="mini-pill" onclick="openLogin('${p.id}', event)" title="클릭하여 ${p.name} 로그인">
            <div class="mini-pill-top">
              <span>${shortName(p.id)}</span>
              <span style="width:6px;height:6px;border-radius:50%;background:#475569;"></span>
            </div>
            <div class="mini-pill-val" style="color:#64748b; font-size:11px;">미연동</div>
            <div class="mini-progress">
              <div class="mini-progress-fill" style="width:0%"></div>
            </div>
          </div>
        `;
      }
      const col = getColor(p.remaining_pct);
      const grad = getGradient(p.remaining_pct);
      const m = getDisplayMetric(p.remaining_pct);
      return `
        <div class="mini-pill" onclick="toggleCard('${p.id}')" title="${p.name} 접기/펼치기">
          <div class="mini-pill-top">
            <span>${shortName(p.id)}</span>
            <span style="width:6px;height:6px;border-radius:50%;background:${col};box-shadow:0 0 6px ${col};"></span>
          </div>
          <div class="mini-pill-val" style="color:${col}">${m.pct}% <span style="font-size:9.5px;font-weight:600;color:#64748b;">${m.tag}</span></div>
          <div class="mini-progress">
            <div class="mini-progress-fill" style="width:${m.width}%; background:${grad}"></div>
          </div>
        </div>
      `;
    }).join("");

    // 2. Account Cards & Inner Collapsible Model Group Boxes
    const container = document.getElementById("cardsContainer");
    container.innerHTML = orderedProviders.map(p => {
      const isCardFolded = !!foldedCards[p.id];
      const chevronFoldClass = isCardFolded ? "folded" : "";

      if (!p.logged_in) {
        const showPaste = openPasteBoxes[p.id] ? "show" : "";
        const placeholder = p.id === "claude"
          ? "로그인 후 화면에 뜬 인증코드 붙여넣기"
          : "WorkosCursorSessionToken 값 붙여넣기";
        const needsPaste = (p.id === "claude" || p.id === "cursor");

        return `
          <div class="card" data-card-id="${p.id}">
            <div class="card-header" onpointerdown="startCardDrag(event, '${p.id}')">
              <div class="provider-left">
                <span class="drag-grip" title="드래그하여 계정 순서 이동">${getGripSvg()}</span>
                <div class="brand-icon brand-${p.id}">${getBrandIconSvg(p.id)}</div>
                <div class="provider-titles">
                  <span class="provider-name">${p.name}</span>
                  <span class="badge">미연동</span>
                </div>
              </div>
              <div class="card-right">
                <div class="chevron-badge ${chevronFoldClass}">▾</div>
              </div>
            </div>
            <div class="card-body ${isCardFolded ? 'folded' : ''}">
              <div class="login-box">
                <button class="login-btn" onclick="openLogin('${p.id}', event)">
                  ${p.login_label || (p.name + " 로그인")}
                </button>
                ${needsPaste ? `
                  <div class="paste-box ${showPaste}" id="paste_${p.id}">
                    <input class="paste-input" id="input_${p.id}" placeholder="${placeholder}" onclick="event.stopPropagation()" />
                    <button class="paste-submit" onclick="submitCodeOrToken('${p.id}', event)">연동</button>
                  </div>
                ` : ""}
                <div class="login-hint">${p.hint || ""}</div>
              </div>
            </div>
          </div>
        `;
      }

      const col = getColor(p.remaining_pct);
      const cardMetric = getDisplayMetric(p.remaining_pct);
      const boxesHtml = (p.boxes || []).map(box => {
        const isBoxFolded = !!foldedBoxes[box.id];
        const bCol = getColor(box.remaining_pct);
        const boxMetric = getDisplayMetric(box.remaining_pct);

        const barsHtml = (box.bars || []).map(bar => {
          const barCol = getColor(bar.remaining_pct);
          const barGrad = getGradient(bar.remaining_pct);
          const barMetric = getDisplayMetric(bar.remaining_pct);
          return `
            <div class="bar-row">
              <div class="bar-top">
                <span class="bar-name">${bar.name}</span>
                <div class="bar-meta">
                  ${bar.reset_text ? `<span class="bar-reset">${bar.reset_text}</span>` : ""}
                  <span class="bar-val" style="color:${barCol}">${barMetric.pct}% ${barMetric.tag}</span>
                </div>
              </div>
              <div class="bar-track">
                <div class="bar-fill" style="width:${barMetric.width}%; background:${barGrad}"></div>
              </div>
            </div>
          `;
        }).join("");

        return `
          <div class="group-box" data-box-id="${box.id}" data-provider-id="${p.id}">
            <div class="box-header" onpointerdown="startBoxDrag(event, '${p.id}', '${box.id}')">
              <div class="box-title-wrap">
                <span class="drag-grip" title="드래그하여 박스 순서 이동">${getGripSvg()}</span>
                <button class="box-title-btn" onpointerdown="event.stopPropagation()" onclick="openBoxModelsModal('${p.id}', '${box.id}', event)" title="사용 가능한 모델 목록 보기">
                  <span>${box.title}</span>
                  ${box.subtitle ? `<span class="info-dot">ⓘ</span>` : ""}
                </button>
              </div>
              <div class="box-right">
                <span class="box-pct-badge" style="color:${bCol}">${boxMetric.pct}% ${boxMetric.tag}</span>
                <span class="box-chevron ${isBoxFolded ? 'folded' : ''}">▾</span>
              </div>
            </div>
            <div class="box-body ${isBoxFolded ? 'folded' : ''}">
              ${barsHtml}
            </div>
          </div>
        `;
      }).join("");

      return `
        <div class="card" data-card-id="${p.id}">
          <div class="card-header" onpointerdown="startCardDrag(event, '${p.id}')">
            <div class="provider-left">
              <span class="drag-grip" title="드래그하여 계정 순서 이동">${getGripSvg()}</span>
              <div class="brand-icon brand-${p.id}">${getBrandIconSvg(p.id)}</div>
              <div class="provider-titles">
                <button class="provider-info-btn" onpointerdown="event.stopPropagation()" onclick="openProviderInfoModal('${p.id}', event)" title="계정 및 플랜 확인">
                  <span class="provider-name">${p.name}</span>
                </button>
                <span class="badge">${p.plan || p.badge || "연동됨"}</span>
                <button class="provider-refresh-btn" data-refresh-provider="${p.id}" title="수동 새로고침 (5초 쿨다운)" onpointerdown="event.stopPropagation()" onclick="refreshProvider('${p.id}', event)">↻</button>
                <button class="logout-btn" title="연동 해제" onpointerdown="event.stopPropagation()" onclick="logoutProvider('${p.id}', event)">✕</button>
              </div>
            </div>
            <div class="card-right">
              <div class="pct-pill">
                <span class="rem-pct" style="color:${col}">${cardMetric.pct}%</span>
                <span class="rem-label">${cardMetric.summaryTag}</span>
              </div>
              <div class="chevron-badge ${chevronFoldClass}">▾</div>
            </div>
          </div>
          <div class="card-body ${isCardFolded ? 'folded' : ''}">
            <div class="boxes-list" id="boxes_${p.id}">
              ${boxesHtml}
            </div>
          </div>
        </div>
      `;
    }).join("");

    Object.keys(savedInputs).forEach(id => {
      const el = document.getElementById("input_" + id);
      if (el) el.value = savedInputs[id];
    });
    applyCooldownUI();
  }

  // =========================================================================
  // POINTER DRAG-AND-DROP FOR ACCOUNT CARDS & INNER MODEL BOXES
  // =========================================================================
  function startCardDrag(e, cardId) {
    if (e.button !== 0) return;
    if (e.target.closest("button") || e.target.closest("input")) return;

    const container = document.getElementById("cardsContainer");
    const cardEl = container.querySelector(`.card[data-card-id="${cardId}"]`);
    if (!cardEl) return;

    const startY = e.clientY;
    let moved = false;

    function onMove(ev) {
      if (Math.abs(ev.clientY - startY) > 5) {
        if (!moved) {
          moved = true;
          isDragging = true;
          cardEl.classList.add("dragging");
        }
        const siblings = Array.from(container.querySelectorAll(".card"));
        for (const sib of siblings) {
          if (sib === cardEl) continue;
          const rect = sib.getBoundingClientRect();
          const midY = rect.top + rect.height / 2;
          if (ev.clientY < midY && cardEl.compareDocumentPosition(sib) & Node.DOCUMENT_POSITION_PRECEDING) {
            container.insertBefore(cardEl, sib);
            break;
          } else if (ev.clientY > midY && cardEl.compareDocumentPosition(sib) & Node.DOCUMENT_POSITION_FOLLOWING) {
            container.insertBefore(cardEl, sib.nextSibling);
            break;
          }
        }
      }
    }

    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      cardEl.classList.remove("dragging");

      if (!moved) {
        isDragging = false;
        toggleCard(cardId);
      } else {
        cardOrder = Array.from(container.querySelectorAll(".card")).map(el => el.getAttribute("data-card-id"));
        isDragging = false;
        syncOrderToBackend();
        if (lastData) render(lastData);
      }
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function startBoxDrag(e, providerId, boxId) {
    e.stopPropagation();
    if (e.button !== 0) return;

    const listEl = document.getElementById("boxes_" + providerId);
    if (!listEl) return;
    const boxEl = listEl.querySelector(`.group-box[data-box-id="${boxId}"]`);
    if (!boxEl) return;

    const startY = e.clientY;
    let moved = false;

    function onMove(ev) {
      if (Math.abs(ev.clientY - startY) > 5) {
        if (!moved) {
          moved = true;
          isDragging = true;
          boxEl.classList.add("dragging");
        }
        const siblings = Array.from(listEl.querySelectorAll(".group-box"));
        for (const sib of siblings) {
          if (sib === boxEl) continue;
          const rect = sib.getBoundingClientRect();
          const midY = rect.top + rect.height / 2;
          if (ev.clientY < midY && boxEl.compareDocumentPosition(sib) & Node.DOCUMENT_POSITION_PRECEDING) {
            listEl.insertBefore(boxEl, sib);
            break;
          } else if (ev.clientY > midY && boxEl.compareDocumentPosition(sib) & Node.DOCUMENT_POSITION_FOLLOWING) {
            listEl.insertBefore(boxEl, sib.nextSibling);
            break;
          }
        }
      }
    }

    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      boxEl.classList.remove("dragging");

      if (!moved) {
        isDragging = false;
        toggleBox(boxId);
      } else {
        boxOrder[providerId] = Array.from(listEl.querySelectorAll(".group-box")).map(el => el.getAttribute("data-box-id"));
        isDragging = false;
        syncOrderToBackend();
        if (lastData) render(lastData);
      }
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  async function refreshNow(force = false, providerId = "") {
    if (isDragging) return;
    if (document.activeElement && document.activeElement.tagName === "INPUT") {
      return;
    }
    const dot = document.getElementById("pulseDot");
    dot.style.background = "#38bdf8";
    const data = await fetchData(force, providerId);
    if (data) render(data);
    setTimeout(() => { dot.style.background = "#10b981"; }, 300);
  }

  async function toggleCompact() {
    compactMode = !compactMode;
    document.body.classList.toggle("compact", compactMode);
    const btn = document.getElementById("btnCompact");
    btn.textContent = compactMode ? "확장" : "미니바";
    btn.classList.toggle("active", compactMode);
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
    document.getElementById("btnPin").classList.toggle("active", alwaysOnTop);
    try {
      await fetch("/api/window", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({always_on_top: alwaysOnTop})
      });
    } catch (e) {}
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showInfoModal(title, bodyHtml) {
    const backdrop = document.getElementById("infoModalBackdrop");
    const titleEl = document.getElementById("infoModalTitle");
    const bodyEl = document.getElementById("infoModalBody");
    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.innerHTML = bodyHtml;
    if (backdrop) backdrop.classList.add("show");
  }

  function closeInfoModal(e) {
    if (e && e.target && e.target.id !== "infoModalBackdrop") return;
    const backdrop = document.getElementById("infoModalBackdrop");
    if (backdrop) backdrop.classList.remove("show");
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
      items = raw
        ? raw.split(/[,·]+/).map(s => s.trim()).filter(Boolean)
        : [(box.title || "모델 정보 없음")];
    }
    let html = items.map(m => `<div class="info-modal-item">• ${escapeHtml(m)}</div>`).join("");
    if (box.note) {
      html += `<div class="info-modal-note">${escapeHtml(box.note)}</div>`;
    }
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
      <div class="info-modal-row">
        <span class="info-modal-label">로그인 계정</span>
        <span class="info-modal-val">${escapeHtml(account)}</span>
      </div>
      <div class="info-modal-row">
        <span class="info-modal-label">플랜</span>
        <span class="info-modal-val">${escapeHtml(plan)}</span>
      </div>
      <div class="info-modal-row">
        <span class="info-modal-label">갱신 / 리셋</span>
        <span class="info-modal-val">${escapeHtml(resetTxt)}</span>
      </div>
    `;
    if (p.note) {
      html += `<div class="info-modal-note">${escapeHtml(p.note)}</div>`;
    }
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
    if (gBtn) {
      const remMs = globalCooldownEnd - now;
      if (remMs > 0) {
        anyActive = true;
        const sec = Math.ceil(remMs / 1000);
        gBtn.disabled = true;
        gBtn.textContent = `${sec}`;
      } else {
        gBtn.disabled = false;
        gBtn.innerHTML = GLOBAL_REFRESH_SVG;
      }
    }

    document.querySelectorAll(".provider-refresh-btn[data-refresh-provider]").forEach(btn => {
      const pid = btn.getAttribute("data-refresh-provider");
      const remMs = (providerCooldownEnd[pid] || 0) - now;
      if (remMs > 0) {
        anyActive = true;
        const sec = Math.ceil(remMs / 1000);
        btn.disabled = true;
        btn.textContent = `${sec}`;
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
    if (!cooldownTickTimer) {
      cooldownTickTimer = setInterval(applyCooldownUI, 200);
    }
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

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeInfoModal();
  });

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
        if (up) up.textContent = `최신 버전 (v${info.current_version})`;
      }
    } catch (e) {}
  }

  function dismissUpdateBanner() {
    const banner = document.getElementById("updateBanner");
    if (banner) banner.classList.remove("show");
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
    updateModeHeaderUI();
    setTimeout(() => refreshNow(false), 120);
    setTimeout(() => checkForUpdates(false), 2000);
    setInterval(() => refreshNow(false), 15000);
  });
</script>
</body>
</html>
"""


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
                    tmp_dir = tempfile.mkdtemp(prefix="ai_quota_login_")
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
        d = base / "TokenChecker"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path.home()


def _setup_logging(cli_mode: bool = False) -> Path:
    rt_dir = _get_runtime_dir()
    log_path = rt_dir / ("widget.log" if platform.system() == "Windows" else ".ai_quota_widget.log")
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
    pid_path = rt_dir / ("widget.pid" if platform.system() == "Windows" else ".ai_quota_widget.pid")
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
                self.window.resize(440, 150 if compact else 740)
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
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            cur_w = max(440, rect.right - rect.left)
                            scale = cur_w / 440.0
                            target_h = int((155 if compact else 740) * scale)
                            user32.SetWindowPos(hwnd, 0, 0, 0, cur_w, target_h, 0x0002 | 0x0004 | 0x0010)
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
                    wf.BrowserView.instances[window.uid] = browser
                    window.events.before_show.set()
                    browser.Show()
                    browser.Activate()
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
                if sys.getwindowsversion().major >= 6:
                    ctypes.windll.user32.SetProcessDPIAware()
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
            [sys.executable, os.path.abspath(__file__), "--server-worker", str(port), str(os.getpid())],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            close_fds=True,
        )
        logging.info(f"Spawned isolated server worker process PID={server_proc.pid} on port {port}")
        url = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                r = requests.get(f"{url}/api/health", timeout=0.3)
                if r.status_code == 200:
                    logging.info(f"Server worker healthy at {url}")
                    break
            except Exception:
                time.sleep(0.1)
    else:
        port = start_background_http_server(17890)
        _ensure_codex_callback_server()
        url = f"http://127.0.0.1:{port}"

    try:
        import webview

        if platform.system() == "Windows":
            _patch_pywebview_winforms_deadlock()

        cfg = load_config()
        window = webview.create_window(
            title=APP_NAME,
            url=url,
            width=468,
            height=740,
            x=40,
            y=60,
            resizable=True,
            on_top=bool(cfg.get("always_on_top", True)),
            background_color="#080a0f",
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
    main()
