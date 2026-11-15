import argparse
import base64
import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
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
<title>AI Quota Monitor</title>
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
    gap: 8px;
    padding: 11px 14px 9px 14px;
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
    gap: 7px;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: -0.02em;
    color: #f1f5f9;
    white-space: nowrap;
    flex-shrink: 0;
    word-break: keep-all;
  }
  .app-logo-badge {
    width: 20px;
    height: 20px;
    border-radius: 6px;
    background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.35);
    flex-shrink: 0;
  }
  .app-logo-badge svg {
    width: 12px;
    height: 12px;
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
  .box-title {
    font-weight: 700;
    font-size: 12px;
    color: #f1f5f9;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }
  .box-subtitle {
    font-size: 10px;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 125px;
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
        <svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round">
          <line x1="4" y1="7" x2="18" y2="7" />
          <line x1="4" y1="12" x2="14" y2="12" />
          <line x1="4" y1="17" x2="20" y2="17" />
        </svg>
      </span>
      <span class="live-indicator" id="pulseDot"></span>
      <span id="appTitleText">AI 모니터 v1.0</span>
    </div>
    <div class="controls">
      <button class="ctrl-btn active" id="btnDisplayMode" onclick="toggleDisplayMode()" title="사용량(%) / 잔여량(%) 표시 기준 전환">사용량 기준</button>
      <button class="ctrl-btn" onclick="toggleAllBoxes()" title="모든 계정/박스 접기·펼치기">접기</button>
      <button class="ctrl-btn" id="btnCompact" onclick="toggleCompact()" title="상단 미니바 모드로 축소">미니바</button>
      <button class="ctrl-btn active" id="btnPin" onclick="togglePin()" title="항상 위에 고정">고정</button>
      <button class="ctrl-btn" onclick="refreshNow(true)" title="강제 새로고침">
        <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>
      </button>
    </div>
  </div>

  <div class="mini-bar" id="miniBar"></div>
  <div class="cards" id="cardsContainer"></div>

  <div class="footer">
    <span>드래그하여 순서 변경 · 클릭하여 접기/펼치기</span>
    <span id="updatedAt">동기화 중...</span>
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
    if (titleEl) titleEl.textContent = "AI 모니터 v1.0";
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
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.save_order(cardOrder, boxOrder);
      } else {
        await fetch("/api/save_order", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({card_order: cardOrder, box_order: boxOrder})
        });
      }
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

  async function fetchData(force = false) {
    try {
      if (window.pywebview && window.pywebview.api) {
        return await window.pywebview.api.get_quotas(force);
      } else {
        const r = await fetch("/api/quotas" + (force ? "?force=1" : ""));
        return await r.json();
      }
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
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.open_login_window(providerId);
    } else {
      await fetch("/api/login/" + providerId, { method: "POST" });
    }
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
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.submit_auth_code(providerId, val);
    } else {
      await fetch("/api/submit_code", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({provider_id: providerId, code: val})
      });
    }
    openPasteBoxes[providerId] = false;
    await refreshNow(true);
  }

  async function logoutProvider(providerId, event) {
    if (event) event.stopPropagation();
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.logout_provider(providerId);
    } else {
      await fetch("/api/logout/" + providerId, { method: "POST" });
    }
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
                <span class="box-title">${box.title}</span>
                ${box.subtitle ? `<span class="box-subtitle">· ${box.subtitle}</span>` : ""}
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
                <span class="provider-name">${p.name}</span>
                <span class="badge">${p.badge || "연동됨"}</span>
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

  async function refreshNow(force = false) {
    if (isDragging) return;
    if (document.activeElement && document.activeElement.tagName === "INPUT") {
      return;
    }
    const dot = document.getElementById("pulseDot");
    dot.style.background = "#38bdf8";
    const data = await fetchData(force);
    if (data) render(data);
    setTimeout(() => { dot.style.background = "#10b981"; }, 300);
  }

  async function toggleCompact() {
    compactMode = !compactMode;
    document.body.classList.toggle("compact", compactMode);
    const btn = document.getElementById("btnCompact");
    btn.textContent = compactMode ? "확장" : "미니바";
    btn.classList.toggle("active", compactMode);
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.set_compact(compactMode);
    }
  }

  async function togglePin() {
    alwaysOnTop = !alwaysOnTop;
    document.getElementById("btnPin").classList.toggle("active", alwaysOnTop);
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.set_always_on_top(alwaysOnTop);
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    updateModeHeaderUI();
    setTimeout(() => refreshNow(false), 120);
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


def _ensure_codex_callback_server():
    try:
        server = HTTPServer(("127.0.0.1", 1455), CodexCallbackHandler)
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
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/quotas":
            qs = urllib.parse.parse_qs(parsed.query)
            force = bool(qs.get("force"))
            data = json.dumps(fetch_all_quotas(force=force), ensure_ascii=False).encode("utf-8")
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

        body = UI_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
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


def start_background_http_server(port: int = 17890) -> int:
    for p in range(port, port + 20):
        try:
            server = HTTPServer(("127.0.0.1", p), LocalHTTPHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            OAUTH_STATE["server_port"] = p
            return p
        except OSError:
            continue
    return 0


def run_cli_summary():
    data = fetch_all_quotas(force=True)
    print(f"\n=== AI 모니터 v1.0 ({data['updated_at']}) ===")
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


def main():
    parser = argparse.ArgumentParser(description="AI Agent Official Quota Floating Widget")
    parser.add_argument("--cli", action="store_true", help="터미널에서 상태 확인")
    args = parser.parse_args()

    if args.cli:
        run_cli_summary()
        return

    port = start_background_http_server(17890)
    _ensure_codex_callback_server()
    url = f"http://127.0.0.1:{port}"

    try:
        import webview

        cfg = load_config()
        window = webview.create_window(
            title="AI 모니터 v1.0",
            url=url,
            js_api=GLOBAL_API,
            width=440,
            height=740,
            x=40,
            y=60,
            resizable=True,
            on_top=bool(cfg.get("always_on_top", True)),
            background_color="#080a0f",
        )
        GLOBAL_API.window = window
        print(f"AI Monitor v1.0 started at {url}")
        webview.start(debug=False)
    except Exception as e:
        print(f"Fallback to browser ({e}): {url}")
        webbrowser.open(url)
        threading.Event().wait()


if __name__ == "__main__":
    main()
