import json
import os
import platform
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_PATH = Path.home() / ".ai_quota_widget.json"

# 1. Antigravity Official OAuth Scopes (Client ID/Secret discovered from local Antigravity installation or config)
AGY_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]

# 2. Claude Code Official OAuth
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_SCOPES = "user:profile user:inference"

# 4. OpenAI Codex CLI Official OAuth
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_SCOPES = "openid profile email offline_access"

# In-memory cache to avoid hammering APIs every 5s (especially Claude 429 rate limits)
_MEM_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 45.0

DEFAULT_CONFIG: Dict[str, Any] = {
    "always_on_top": True,
    "compact_mode": False,
    "card_order": ["antigravity", "claude", "cursor", "codex"],
    "box_order": {},
    "cached_providers": {},
    "auth": {
        "antigravity": {
            "access_token": "",
            "refresh_token": "",
            "expires_at": 0,
            "email": "",
            "project_id": "",
        },
        "claude": {
            "access_token": "",
            "refresh_token": "",
            "expires_at": 0,
            "session_key": "",
            "org_id": "",
        },
        "cursor": {
            "session_token": "",
        },
        "codex": {
            "access_token": "",
            "refresh_token": "",
            "expires_at": 0,
        },
    },
}


def load_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k == "auth" and isinstance(v, dict):
                    for pk, pv in v.items():
                        if pk in cfg["auth"] and isinstance(pv, dict):
                            cfg["auth"][pk].update(pv)
                elif k in ("box_order", "cached_providers") and isinstance(v, dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception:
            pass
    return cfg


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    for k, v in updates.items():
        if k == "auth" and isinstance(v, dict):
            for pk, pv in v.items():
                if pk in cfg["auth"] and isinstance(pv, dict):
                    for ak, av in pv.items():
                        # Never overwrite existing non-empty tokens/keys with an empty value during partial updates
                        if av == "" and cfg["auth"][pk].get(ak):
                            continue
                        cfg["auth"][pk][ak] = av
        elif k in ("box_order", "cached_providers") and isinstance(v, dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return cfg


def invalidate_provider_cache(provider_id: Optional[str] = None) -> None:
    if provider_id:
        _MEM_CACHE.pop(provider_id, None)
    else:
        _MEM_CACHE.clear()


def clear_provider_auth(provider_id: str) -> Dict[str, Any]:
    _MEM_CACHE.pop(provider_id, None)
    cfg = load_config()
    if provider_id in cfg["auth"]:
        for k in cfg["auth"][provider_id]:
            if k in ("client_id", "client_secret"):
                continue
            cfg["auth"][provider_id][k] = 0 if k == "expires_at" else ""
    if "cached_providers" in cfg and provider_id in cfg["cached_providers"]:
        cfg["cached_providers"].pop(provider_id, None)
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return cfg


def _get_cached_provider(cfg: Dict[str, Any], provider_id: str, force: bool = False) -> Optional[Dict[str, Any]]:
    if force:
        return None
    entry = _MEM_CACHE.get(provider_id)
    if entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL_SECONDS:
        return entry.get("data")
    return None


def _store_cached_provider(provider_id: str, data: Dict[str, Any]) -> None:
    _MEM_CACHE[provider_id] = {"ts": time.time(), "data": data}
    save_config({"cached_providers": {provider_id: data}})


def _get_fallback_cached_provider(cfg: Dict[str, Any], provider_id: str) -> Optional[Dict[str, Any]]:
    if provider_id in _MEM_CACHE and _MEM_CACHE[provider_id].get("data"):
        return _MEM_CACHE[provider_id]["data"]
    disk_cache = (cfg.get("cached_providers") or {}).get(provider_id)
    if isinstance(disk_cache, dict) and disk_cache.get("logged_in"):
        return disk_cache
    return None


def _parse_iso(ts_val: Any) -> Optional[datetime]:
    if not ts_val:
        return None
    if isinstance(ts_val, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts_val), tz=timezone.utc)
        except Exception:
            return None
    if not isinstance(ts_val, str):
        return None
    try:
        s = ts_val.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _format_reset_countdown(reset_dt: Optional[datetime]) -> str:
    if not reset_dt:
        return ""
    now = datetime.now(timezone.utc)
    diff = (reset_dt - now).total_seconds()
    if diff <= 0:
        return "곧 리셋"
    hours = int(diff // 3600)
    mins = int((diff % 3600) // 60)
    if hours >= 24:
        days = hours // 24
        rem_h = hours % 24
        return f"{days}일 {rem_h}시간 후 리셋"
    elif hours > 0:
        return f"{hours}시간 {mins}분 후 리셋"
    return f"{mins}분 후 리셋"


# =====================================================================
# 1. ANTIGRAVITY (AGY) OFFICIAL QUOTA (3 REPRESENTATIVE BOXES, 6 BARS)
# =====================================================================
def get_agy_oauth_client(cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    env_id = os.environ.get("AGY_CLIENT_ID", "").strip()
    env_sec = os.environ.get("AGY_CLIENT_SECRET", "").strip()
    if env_id.startswith("1071006060591-") and len(env_sec) == 35:
        return env_id, env_sec

    if cfg is None:
        cfg = load_config()
    agy_auth = cfg.get("auth", {}).get("antigravity", {})
    cid = agy_auth.get("client_id", "").strip()
    csec = agy_auth.get("client_secret", "").strip()
    if cid.startswith("1071006060591-") and len(csec) == 35 and csec.startswith("GOCSPX-K58"):
        return cid, csec

    # Auto-detect from local Antigravity IDE installation on macOS / Windows / Linux
    candidates: List[Path] = []
    sys_name = platform.system()
    if sys_name == "Darwin":
        candidates.extend([
            Path("/Applications/Antigravity.app/Contents/Resources/bin/language_server"),
            Path.home() / "Applications/Antigravity.app/Contents/Resources/bin/language_server",
        ])
    elif sys_name == "Windows":
        local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        prog_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        candidates.extend([
            local_app / "Programs/Antigravity/resources/bin/language_server.exe",
            local_app / "Programs/Antigravity/resources/app/extensions/antigravity/bin/language_server_windows_x64.exe",
            local_app / "Programs/Antigravity/resources/app/extensions/antigravity/bin/language_server.exe",
            local_app / "Antigravity/resources/bin/language_server.exe",
            prog_files / "Antigravity/resources/bin/language_server.exe",
        ])
    else:
        candidates.extend([
            Path("/usr/share/antigravity/resources/bin/language_server"),
            Path("/opt/Antigravity/resources/bin/language_server"),
        ])

    for bin_path in candidates:
        if bin_path.exists():
            try:
                raw = bin_path.read_bytes()
                m_id = re.search(rb"1071006060591-[a-z0-9]+\.apps\.googleusercontent\.com", raw)
                m_sec = re.search(rb"GOCSPX-K58[A-Za-z0-9_-]{25}", raw)
                if m_id and m_sec:
                    cid = m_id.group(0).decode("ascii")
                    csec = m_sec.group(0).decode("ascii")
                    save_config({"auth": {"antigravity": {"client_id": cid, "client_secret": csec}}})
                    return cid, csec
            except Exception:
                pass

    return cid, csec


def _get_agy_valid_token(cfg: Dict[str, Any], force_refresh: bool = False) -> Optional[str]:
    agy_auth = cfg.get("auth", {}).get("antigravity", {})
    acc = agy_auth.get("access_token", "")
    ref = agy_auth.get("refresh_token", "")
    exp = float(agy_auth.get("expires_at") or 0)

    if not force_refresh and acc and time.time() < exp - 60:
        return acc

    if ref:
        cid, csec = get_agy_oauth_client(cfg)
        if cid and csec:
            try:
                r = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": cid,
                        "client_secret": csec,
                        "refresh_token": ref,
                        "grant_type": "refresh_token",
                    },
                    timeout=4.0,
                )
                if r.status_code == 200:
                    td = r.json()
                    new_acc = td.get("access_token", "")
                    expires_in = int(td.get("expires_in", 3600))
                    if new_acc:
                        save_config({
                            "auth": {
                                "antigravity": {
                                    "access_token": new_acc,
                                    "expires_at": int(time.time() + expires_in),
                                }
                            }
                        })
                        return new_acc
            except Exception:
                pass
    return acc if acc else None


def fetch_antigravity_usage(cfg: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    cached = _get_cached_provider(cfg, "antigravity", force=force)
    if cached:
        return cached

    boxes: List[Dict[str, Any]] = []
    earliest_reset: Optional[datetime] = None
    email = cfg.get("auth", {}).get("antigravity", {}).get("email", "")

    token = _get_agy_valid_token(cfg)
    if token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/2.32.1",
        }
        base_url = "https://daily-cloudcode-pa.googleapis.com"

        models_map: Dict[str, Any] = {}
        try:
            r_mod = requests.post(
                f"{base_url}/v1internal:fetchAvailableModels",
                headers=headers,
                json={},
                timeout=3.5,
            )
            if r_mod.status_code == 200:
                models_map = r_mod.json().get("models") or {}
        except Exception:
            pass

        def _base_model_name(name: str) -> str:
            return re.sub(
                r"\s*\((?:High|Medium|Low)(?:\s*/\s*(?:High|Medium|Low))*\)\s*$",
                "",
                name.strip(),
                flags=re.IGNORECASE,
            ).strip()

        google_models: List[str] = []
        other_models: List[str] = []
        for mid, mobj in models_map.items():
            if not isinstance(mobj, dict) or mobj.get("isInternal"):
                continue
            dname = _base_model_name(mobj.get("displayName") or "")
            if not dname:
                continue
            prov = (mobj.get("modelProvider") or "").upper()
            if "GOOGLE" in prov or mid.lower().startswith("gemini"):
                if dname not in google_models:
                    google_models.append(dname)
            else:
                if dname not in other_models:
                    other_models.append(dname)

        try:
            r_sum = requests.post(
                f"{base_url}/v1internal:retrieveUserQuotaSummary",
                headers=headers,
                json={},
                timeout=4.0,
            )
            if r_sum.status_code == 401:
                token = _get_agy_valid_token(cfg, force_refresh=True)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    r_sum = requests.post(
                        f"{base_url}/v1internal:retrieveUserQuotaSummary",
                        headers=headers,
                        json={},
                        timeout=4.0,
                    )
            if r_sum.status_code == 200:
                qd = r_sum.json()
                groups = qd.get("groups") or (qd.get("response") or {}).get("groups") or []
                for idx, g in enumerate(groups):
                    g_name = g.get("displayName") or f"Model Group {idx + 1}"
                    g_desc = g.get("description") or ""
                    if ":" in g_desc:
                        g_desc = g_desc.split(":", 1)[1].strip()

                    bars: List[Dict[str, Any]] = []
                    for b in g.get("buckets") or []:
                        rem_val = b.get("remainingFraction")
                        if rem_val is None and isinstance(b.get("remaining"), dict):
                            rem_val = b["remaining"].get("remainingFraction") or b["remaining"].get("value")
                        if rem_val is not None:
                            pct = round(float(rem_val) * 100.0, 1)
                            r_dt = _parse_iso(b.get("resetTime"))
                            if r_dt and (earliest_reset is None or r_dt < earliest_reset):
                                earliest_reset = r_dt
                            win = (b.get("window") or b.get("displayName") or "").lower()
                            if "weekly" in win:
                                bar_label = "주간 한도 (Weekly)"
                            elif "5h" in win or "five hour" in win:
                                bar_label = "5시간 한도 (5h)"
                            else:
                                bar_label = b.get("displayName") or "한도"
                            r_txt = _format_reset_countdown(r_dt)
                            bars.append({
                                "name": bar_label,
                                "remaining_pct": pct,
                                "reset_text": r_txt or "정상",
                                "detail": f"{pct}%",
                            })

                    if bars:
                        # Sort so 5-Hour Limit (5h) is on TOP (first) and Weekly Limit is on BOTTOM (second)
                        bars.sort(key=lambda x: 0 if "5시간" in x["name"] or "5h" in x["name"].lower() else 1)
                        box_min = min(bar["remaining_pct"] for bar in bars)
                        title_lower = g_name.lower()
                        desc_models = [s.strip() for s in g_desc.split(",") if s.strip()] if g_desc else []
                        if "gemini" in title_lower and "argon" not in title_lower:
                            box_models = list(dict.fromkeys(google_models + desc_models))
                        elif "claude" in title_lower or "gpt" in title_lower:
                            box_models = list(dict.fromkeys(other_models + desc_models))
                        else:
                            box_models = desc_models

                        boxes.append({
                            "id": f"agy_box_{idx}",
                            "title": g_name,
                            "subtitle": ", ".join(box_models) if box_models else g_desc,
                            "models": box_models,
                            "note": "Google 외부 OAuth API가 제공하는 모델만 표시됩니다. (Gemini 4 Argon / Hydrogen 등 IDE 내부 모델은 API에서 제공되지 않음)",
                            "remaining_pct": box_min,
                            "bars": bars[:2],
                        })
        except Exception:
            pass

    if boxes:
        plan_name = cfg.get("auth", {}).get("antigravity", {}).get("plan", "")
        if not plan_name and token:
            try:
                r_tier = requests.post(
                    f"{base_url}/v1internal:loadCodeAssist",
                    headers=headers,
                    json={"metadata": {"ideType": "ANTIGRAVITY"}},
                    timeout=2.5,
                )
                if r_tier.status_code == 200:
                    td = r_tier.json()
                    tier_obj = td.get("paidTier") or td.get("currentTier") or {}
                    plan_name = (tier_obj.get("name") or tier_obj.get("id") or "").strip()
                    if plan_name:
                        save_config({"auth": {"antigravity": {"plan": plan_name}}})
            except Exception:
                pass
        if not plan_name:
            plan_name = "Google AI"

        primary_rem = min(b["remaining_pct"] for b in boxes)
        total_bars = sum(len(b.get("bars", [])) for b in boxes)
        res = {
            "id": "antigravity",
            "name": "Antigravity",
            "logged_in": True,
            "badge": plan_name,
            "plan": plan_name,
            "account": email or "Google OAuth",
            "note": "Google 외부 OAuth API 기준 사용량만 표시됩니다. (Gemini 4 Argon / Hydrogen 등 IDE 내부 모델은 API 미제공)",
            "remaining_pct": primary_rem,
            "reset_text": _format_reset_countdown(earliest_reset) or "실시간 연동",
            "headline": f"대표 모델 {len(boxes)}개 그룹 ({total_bars}개 바)",
            "boxes": boxes,
        }
        _store_cached_provider("antigravity", res)
        return res

    if token:
        fb = _get_fallback_cached_provider(cfg, "antigravity")
        if fb:
            return fb

    return {
        "id": "antigravity",
        "name": "Antigravity",
        "logged_in": False,
        "login_label": "Google 계정으로 로그인",
        "hint": "클릭 시 Google 로그인 창이 열리며 완료 시 자동으로 닫힙니다.",
    }


# =====================================================================
# 2. CLAUDE OFFICIAL QUOTA (WITH RATE-LIMIT PROTECTION & PERSISTENT CACHE)
# =====================================================================
def _refresh_claude_token(ref: str) -> Optional[str]:
    if not ref:
        return None
    try:
        r = requests.post(
            "https://console.anthropic.com/v1/oauth/token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": ref,
                "client_id": CLAUDE_CLIENT_ID,
            },
            headers={"Content-Type": "application/json"},
            timeout=4.0,
        )
        if r.status_code == 200:
            td = r.json()
            new_acc = td.get("access_token", "")
            new_ref = td.get("refresh_token", ref)
            expires_in = int(td.get("expires_in", 3600))
            if new_acc:
                save_config({
                    "auth": {
                        "claude": {
                            "access_token": new_acc,
                            "refresh_token": new_ref,
                            "expires_at": int(time.time() + expires_in),
                        }
                    }
                })
                return new_acc
    except Exception:
        pass
    return None


def _get_claude_valid_token(cfg: Dict[str, Any], force_refresh: bool = False) -> Optional[str]:
    c_auth = cfg.get("auth", {}).get("claude", {})
    acc = c_auth.get("access_token", "")
    ref = c_auth.get("refresh_token", "")
    exp = float(c_auth.get("expires_at") or 0)

    if force_refresh and ref:
        refreshed = _refresh_claude_token(ref)
        if refreshed:
            return refreshed

    if acc and (exp == 0 or time.time() < exp - 60):
        return acc

    if ref:
        refreshed = _refresh_claude_token(ref)
        if refreshed:
            return refreshed

    if acc:
        return acc

    home = Path.home()
    for cf in [home / ".claude" / ".credentials.json", home / ".claude" / "credentials.json"]:
        if cf.exists():
            try:
                d = json.loads(cf.read_text(encoding="utf-8"))
                tok = (d.get("claudeAiOauth") or {}).get("accessToken") or d.get("accessToken")
                if tok:
                    return tok
            except Exception:
                pass
    return None


def fetch_claude_usage(cfg: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    cached = _get_cached_provider(cfg, "claude", force=force)
    if cached:
        return cached

    oauth_token = _get_claude_valid_token(cfg)
    c_auth = cfg.get("auth", {}).get("claude", {})
    session_key = c_auth.get("session_key", "").strip()
    org_id = c_auth.get("org_id", "").strip()

    usage_data = None
    usage_is_oauth = False
    badge = "Claude 연동됨"

    if oauth_token:
        try:
            r = requests.get(
                "https://api.anthropic.com/api/oauth/usage",
                headers={
                    "Authorization": f"Bearer {oauth_token}",
                    "anthropic-beta": "oauth-2025-04-20",
                    "User-Agent": "claude-code/2.0.0",
                    "Accept": "application/json",
                },
                timeout=4.0,
            )
            # If 401 or 429 rate-limited, try refreshing the OAuth token once
            if r.status_code in (401, 429):
                new_tok = _get_claude_valid_token(cfg, force_refresh=True)
                if new_tok and new_tok != oauth_token:
                    oauth_token = new_tok
                    r = requests.get(
                        "https://api.anthropic.com/api/oauth/usage",
                        headers={
                            "Authorization": f"Bearer {oauth_token}",
                            "anthropic-beta": "oauth-2025-04-20",
                            "User-Agent": "claude-code/2.0.0",
                            "Accept": "application/json",
                        },
                        timeout=4.0,
                    )
            if r.status_code == 200:
                usage_data = r.json()
                usage_is_oauth = True
                badge = "Claude Pro / Max"
        except Exception:
            pass

    if not usage_data and session_key:
        headers = {
            "Cookie": f"sessionKey={session_key}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        try:
            if not org_id:
                r_org = requests.get("https://claude.ai/api/organizations", headers=headers, timeout=3.5)
                if r_org.status_code == 200:
                    orgs = r_org.json()
                    if isinstance(orgs, list) and len(orgs) > 0:
                        org_id = orgs[0].get("uuid") or ""
                        if org_id:
                            save_config({"auth": {"claude": {"org_id": org_id}}})
            if org_id:
                r_use = requests.get(
                    f"https://claude.ai/api/organizations/{org_id}/usage",
                    headers=headers,
                    timeout=3.5,
                )
                if r_use.status_code == 200:
                    usage_data = r_use.json()
                    badge = "claude.ai"
        except Exception:
            pass

    if usage_data and isinstance(usage_data, dict):
        bars = []
        fh = usage_data.get("five_hour") or {}
        sd = usage_data.get("seven_day") or {}
        sd_opus = usage_data.get("seven_day_opus") or {}
        sd_sonnet = usage_data.get("seven_day_sonnet") or {}

        for key_label, bucket_obj in [
            ("5시간 한도 (5h)", fh),
            ("주간 한도 (Weekly)", sd),
            ("Opus 주간 한도", sd_opus),
            ("Sonnet 주간 한도", sd_sonnet),
        ]:
            if isinstance(bucket_obj, dict) and bucket_obj.get("utilization") is not None:
                u = float(bucket_obj["utilization"])
                if usage_is_oauth:
                    used_pct = u
                else:
                    used_pct = u if u > 1.0 else u * 100.0
                rem_val = round(max(0.0, 100.0 - used_pct), 1)
                r_txt = _format_reset_countdown(_parse_iso(bucket_obj.get("resets_at")))
                bars.append({
                    "name": key_label,
                    "remaining_pct": rem_val,
                    "reset_text": r_txt or "진행중",
                    "detail": f"{rem_val}%",
                })

        if bars:
            primary_rem = min(b["remaining_pct"] for b in bars)
            boxes = [
                {
                    "id": "claude_box_main",
                    "title": "Claude Models",
                    "subtitle": "Claude Opus 4 / Sonnet 4",
                    "remaining_pct": primary_rem,
                    "bars": bars,
                }
            ]
            claude_acc = c_auth.get("email") or ("Anthropic OAuth" if oauth_token else "세션 키 연동")
            res = {
                "id": "claude",
                "name": "Claude",
                "logged_in": True,
                "badge": badge,
                "plan": badge,
                "account": claude_acc,
                "remaining_pct": primary_rem,
                "reset_text": bars[0].get("reset_text", "자동 갱신"),
                "headline": f"주간/5시간 한도 연동됨",
                "boxes": boxes,
            }
            _store_cached_provider("claude", res)
            return res

    # CRITICAL FIX: Never drop to logged_in=False if we have a token or session_key!
    if oauth_token or session_key:
        fb = _get_fallback_cached_provider(cfg, "claude")
        if fb:
            _MEM_CACHE["claude"] = {"ts": time.time(), "data": fb}
            return fb

    return {
        "id": "claude",
        "name": "Claude",
        "logged_in": False,
        "login_label": "Claude 공식 로그인",
        "hint": "클릭 후 열리는 창에서 승인 후 나오는 인증코드를 붙여넣으면 연동됩니다.",
    }


# =====================================================================
# 3. CURSOR OFFICIAL QUOTA
# =====================================================================
def _extract_cursor_local_token() -> Optional[str]:
    home = Path.home()
    sys_name = platform.system()
    if sys_name == "Darwin":
        db_path = home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    elif sys_name == "Windows":
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        db_path = Path(appdata) / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    else:
        db_path = home / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"

    if db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.5)
            cur = conn.cursor()
            cur.execute("SELECT value FROM ItemTable WHERE key = 'cursorAuth/accessToken' LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                return str(row[0]).strip()
        except Exception:
            pass
    return None


def fetch_cursor_usage(cfg: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    cached = _get_cached_provider(cfg, "cursor", force=force)
    if cached:
        return cached

    token = cfg.get("auth", {}).get("cursor", {}).get("session_token", "").strip() or _extract_cursor_local_token()
    if token:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Cookie": f"WorkosCursorSessionToken={token}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
            resp = requests.get("https://www.cursor.com/api/usage", headers=headers, timeout=3.5)
            if resp.status_code == 200:
                data = resp.json()
                bars = []
                primary_rem = None
                start_dt = _parse_iso(data.get("startOfMonth"))
                reset_dt = (start_dt + timedelta(days=30)) if start_dt else None
                r_txt = _format_reset_countdown(reset_dt) or "월간 주기"

                for m_key, label in [
                    ("gpt-4", "Premium (Fast Requests)"),
                    ("gpt-3.5-turbo", "Standard Requests"),
                    ("gpt-4-32k", "Long Context Requests"),
                ]:
                    m_obj = data.get(m_key)
                    if isinstance(m_obj, dict) and m_obj.get("maxRequestUsage"):
                        used = int(m_obj.get("numRequests") or 0)
                        limit = int(m_obj.get("maxRequestUsage") or 500)
                        rem = max(0, limit - used)
                        pct = round((rem / max(1, limit)) * 100.0, 1)
                        if primary_rem is None:
                            primary_rem = pct
                        bars.append({
                            "name": label,
                            "remaining_pct": pct,
                            "reset_text": f"{rem}/{limit}회",
                            "detail": f"{pct}%",
                        })

                if primary_rem is not None:
                    boxes = [
                        {
                            "id": "cursor_box_main",
                            "title": "Cursor Requests",
                            "subtitle": "월간 Fast / Standard 한도",
                            "remaining_pct": primary_rem,
                            "bars": bars,
                        }
                    ]
                    res = {
                        "id": "cursor",
                        "name": "Cursor",
                        "logged_in": True,
                        "badge": "Cursor Pro",
                        "plan": "Cursor Pro",
                        "account": cfg.get("auth", {}).get("cursor", {}).get("email") or "Cursor 세션 연동",
                        "remaining_pct": primary_rem,
                        "reset_text": r_txt,
                        "headline": f"Fast Requests {primary_rem}% 남음",
                        "boxes": boxes,
                    }
                    _store_cached_provider("cursor", res)
                    return res
        except Exception:
            pass

        fb = _get_fallback_cached_provider(cfg, "cursor")
        if fb:
            return fb

    return {
        "id": "cursor",
        "name": "Cursor",
        "logged_in": False,
        "login_label": "Cursor 로그인",
        "hint": "Cursor 앱 로그인 시 자동 연동되거나, 팝업창에서 세션 토큰을 붙여넣어 연동할 수 있습니다.",
    }


# =====================================================================
# 4. CHATGPT / CODEX OFFICIAL QUOTA
# =====================================================================
def _get_codex_valid_token(cfg: Dict[str, Any]) -> Optional[str]:
    cx = cfg.get("auth", {}).get("codex", {})
    acc = cx.get("access_token", "").strip()
    ref = cx.get("refresh_token", "").strip()
    exp = float(cx.get("expires_at") or 0)

    if acc and (exp == 0 or time.time() < exp - 60):
        return acc

    if ref:
        try:
            r = requests.post(
                "https://auth.openai.com/oauth/token",
                json={
                    "client_id": CODEX_CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": ref,
                },
                headers={"Content-Type": "application/json"},
                timeout=4.0,
            )
            if r.status_code == 200:
                td = r.json()
                new_acc = td.get("access_token", "")
                new_ref = td.get("refresh_token", ref)
                expires_in = int(td.get("expires_in", 3600))
                if new_acc:
                    save_config({
                        "auth": {
                            "codex": {
                                "access_token": new_acc,
                                "refresh_token": new_ref,
                                "expires_at": int(time.time() + expires_in),
                            }
                        }
                    })
                    return new_acc
        except Exception:
            pass

    if acc:
        return acc

    auth_file = Path.home() / ".codex" / "auth.json"
    if auth_file.exists():
        try:
            d = json.loads(auth_file.read_text(encoding="utf-8"))
            tok = (d.get("tokens") or {}).get("access_token") or d.get("access_token")
            if tok:
                return str(tok).strip()
        except Exception:
            pass
    return None


def fetch_codex_usage(cfg: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    cached = _get_cached_provider(cfg, "codex", force=force)
    if cached:
        return cached

    token = _get_codex_valid_token(cfg)
    if token:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
            resp = requests.get("https://chatgpt.com/backend-api/wham/usage", headers=headers, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                rl = data.get("rate_limit") or {}
                pw = rl.get("primary_window") or rl.get("five_hour") or {}
                sw = rl.get("secondary_window") or rl.get("seven_day") or {}

                bars = []
                if pw:
                    if "used_percent" in pw:
                        rem_p = round(max(0.0, 100.0 - float(pw["used_percent"])), 1)
                    elif "remaining" in pw and "limit" in pw and float(pw["limit"]) > 0:
                        rem_p = round((float(pw["remaining"]) / float(pw["limit"])) * 100.0, 1)
                    else:
                        rem_p = 100.0
                    r_str = _format_reset_countdown(_parse_iso(pw.get("reset_at")))
                    bars.append({
                        "name": "5시간 한도 (5h)",
                        "remaining_pct": rem_p,
                        "reset_text": r_str or "진행중",
                        "detail": f"{rem_p}%",
                    })

                if sw and "used_percent" in sw:
                    rem_s = round(max(0.0, 100.0 - float(sw["used_percent"])), 1)
                    r_str_s = _format_reset_countdown(_parse_iso(sw.get("reset_at")))
                    bars.append({
                        "name": "주간 한도 (Weekly)",
                        "remaining_pct": rem_s,
                        "reset_text": r_str_s or "진행중",
                        "detail": f"{rem_s}%",
                    })

                if bars:
                    primary_rem = min(b["remaining_pct"] for b in bars)
                    boxes = [
                        {
                            "id": "codex_box_main",
                            "title": "GPT / Codex Models",
                            "subtitle": "주간 및 5시간 한도",
                            "remaining_pct": primary_rem,
                            "bars": bars,
                        }
                    ]
                    codex_plan = (data.get("plan_type") or "Codex OAuth").upper()
                    codex_acc = cfg.get("auth", {}).get("codex", {}).get("email") or "OpenAI OAuth"
                    res = {
                        "id": "codex",
                        "name": "ChatGPT / Codex",
                        "logged_in": True,
                        "badge": codex_plan,
                        "plan": codex_plan,
                        "account": codex_acc,
                        "remaining_pct": primary_rem,
                        "reset_text": bars[0].get("reset_text", "자동 갱신"),
                        "headline": f"최저 {primary_rem}% 남음",
                        "boxes": boxes,
                    }
                    _store_cached_provider("codex", res)
                    return res
        except Exception:
            pass

        fb = _get_fallback_cached_provider(cfg, "codex")
        if fb:
            return fb

    return {
        "id": "codex",
        "name": "ChatGPT / Codex",
        "logged_in": False,
        "login_label": "ChatGPT / Codex 공식 로그인",
        "hint": "클릭 시 OpenAI 로그인 창이 열리며 완료 시 자동으로 닫힙니다.",
    }


def fetch_all_quotas(force: bool = False, force_provider: str = "") -> Dict[str, Any]:
    cfg = load_config()
    fp = (force_provider or "").strip().lower()
    raw_map = {
        "antigravity": fetch_antigravity_usage(cfg, force=(force and (not fp or fp == "antigravity"))),
        "claude": fetch_claude_usage(cfg, force=(force and (not fp or fp == "claude"))),
        "cursor": fetch_cursor_usage(cfg, force=(force and (not fp or fp == "cursor"))),
        "codex": fetch_codex_usage(cfg, force=(force and (not fp or fp == "codex"))),
    }

    # Apply saved card order
    saved_card_order = cfg.get("card_order") or ["antigravity", "claude", "cursor", "codex"]
    ordered_ids = [pid for pid in saved_card_order if pid in raw_map] + [
        pid for pid in raw_map if pid not in saved_card_order
    ]

    # Apply saved box order inside each provider & ensure 5h bar is always above Weekly bar
    saved_box_orders = cfg.get("box_order") or {}
    providers = []
    for pid in ordered_ids:
        p_obj = raw_map[pid]
        if p_obj.get("boxes"):
            for box in p_obj["boxes"]:
                if box.get("bars"):
                    box["bars"].sort(key=lambda x: 0 if ("5시간" in x.get("name", "") or "5h" in x.get("name", "").lower()) else 1)
            if pid in saved_box_orders:
                b_order = saved_box_orders[pid]
                b_map = {b["id"]: b for b in p_obj["boxes"]}
                ordered_boxes = [b_map[bid] for bid in b_order if bid in b_map] + [
                    b for b in p_obj["boxes"] if b["id"] not in b_order
                ]
                p_obj["boxes"] = ordered_boxes
        providers.append(p_obj)

    return {
        "updated_at": datetime.now().strftime("%H:%M:%S"),
        "platform": f"{platform.system()} ({platform.machine()})",
        "card_order": ordered_ids,
        "box_order": saved_box_orders,
        "providers": providers,
    }
