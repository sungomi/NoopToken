import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import requests

APP_NAME = "토큰체커"
APP_EN_NAME = "TokenChecker"
APP_VERSION = "1.1.0"
GITHUB_REPO = "sungomi/TokenChecker"

_CACHE_LOCK = threading.Lock()
_CHECK_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_UPDATE_STATUS: Dict[str, Any] = {
    "state": "idle",  # idle | downloading | applying | error | done
    "progress": 0,
    "message": "",
}


def parse_version(ver: str) -> Tuple[int, ...]:
    """Parse a semantic version string like 'v1.2.0' into a comparable integer tuple."""
    clean = (ver or "").strip().lstrip("vV")
    parts = []
    for seg in clean.split("."):
        digits = ""
        for ch in seg:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _select_asset(assets: list) -> Tuple[str, str]:
    """Select the best release asset (name, browser_download_url) for the current OS."""
    sys_name = platform.system()
    if sys_name == "Darwin":
        for ext in (".dmg", ".zip"):
            for a in assets:
                name = str(a.get("name") or "")
                url = str(a.get("browser_download_url") or "")
                if name.lower().endswith(ext) and url:
                    return name, url
    elif sys_name == "Windows":
        for a in assets:
            name = str(a.get("name") or "")
            url = str(a.get("browser_download_url") or "")
            if name.lower().endswith(".exe") and url:
                return name, url
    return "", ""


def check_for_update(force: bool = False) -> Dict[str, Any]:
    """Check GitHub Releases for a newer version of TokenChecker."""
    now = time.time()
    with _CACHE_LOCK:
        if not force and _CHECK_CACHE["data"] and (now - _CHECK_CACHE["ts"] < 900):
            return dict(_CHECK_CACHE["data"])

    result: Dict[str, Any] = {
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "update_available": False,
        "release_url": f"https://github.com/{GITHUB_REPO}/releases/latest",
        "asset_name": "",
        "asset_url": "",
        "is_frozen": bool(getattr(sys, "frozen", False)),
        "can_auto_update": False,
        "error": "",
    }
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_EN_NAME}/{APP_VERSION}",
            },
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            tag = str(data.get("tag_name") or "").strip()
            latest_ver = tag.lstrip("vV") or APP_VERSION
            is_newer = parse_version(latest_ver) > parse_version(APP_VERSION)
            asset_name, asset_url = _select_asset(data.get("assets") or [])
            result.update({
                "latest_version": latest_ver,
                "update_available": is_newer,
                "release_url": str(data.get("html_url") or result["release_url"]),
                "asset_name": asset_name,
                "asset_url": asset_url,
                "can_auto_update": bool(getattr(sys, "frozen", False) and asset_url),
            })
        elif resp.status_code == 404:
            result["error"] = "릴리즈 없음"
        else:
            result["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        result["error"] = str(e)

    with _CACHE_LOCK:
        _CHECK_CACHE["ts"] = now
        _CHECK_CACHE["data"] = dict(result)
    return result


def get_update_status() -> Dict[str, Any]:
    with _CACHE_LOCK:
        return dict(_UPDATE_STATUS)


def _set_status(state: str, progress: int = 0, message: str = "") -> None:
    with _CACHE_LOCK:
        _UPDATE_STATUS["state"] = state
        _UPDATE_STATUS["progress"] = progress
        _UPDATE_STATUS["message"] = message


def _download_file(url: str, dest_path: Path) -> None:
    with requests.get(
        url,
        stream=True,
        timeout=30.0,
        headers={"User-Agent": f"{APP_EN_NAME}/{APP_VERSION}"},
    ) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = min(99, int(downloaded * 100 / total))
                    _set_status("downloading", pct, f"다운로드 중... {pct}%")
                else:
                    mb = downloaded / (1024 * 1024)
                    _set_status("downloading", 50, f"다운로드 중... {mb:.1f}MB")


def _apply_macos_update(asset_path: Path, tmp_dir: Path) -> None:
    exe_path = Path(sys.executable).resolve()
    app_bundle: Optional[Path] = None
    for parent in exe_path.parents:
        if parent.suffix == ".app":
            app_bundle = parent
            break
    if not app_bundle or not app_bundle.exists():
        raise RuntimeError("현재 실행 중인 .app 번들 경로를 찾을 수 없습니다.")

    _set_status("applying", 100, "업데이트 압축 해제 중...")
    staged_app = tmp_dir / f"{APP_EN_NAME}.app"

    if asset_path.suffix.lower() == ".dmg":
        mnt_dir = tmp_dir / "mnt"
        mnt_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt_dir), str(asset_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            apps = list(mnt_dir.glob("*.app"))
            if not apps:
                raise RuntimeError("DMG 내부에서 .app 파일을 찾지 못했습니다.")
            subprocess.run(["ditto", str(apps[0]), str(staged_app)], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mnt_dir), "-quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ditto", "-x", "-k", str(asset_path), str(extract_dir)], check=True)
        apps = list(extract_dir.rglob("*.app"))
        if not apps:
            raise RuntimeError("ZIP 내부에서 .app 파일을 찾지 못했습니다.")
        subprocess.run(["ditto", str(apps[0]), str(staged_app)], check=True)

    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(staged_app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    target_app = app_bundle
    if not os.access(target_app.parent, os.W_OK):
        # Fallback: open the downloaded file so user can drag manually
        subprocess.Popen(["open", str(asset_path)])
        raise RuntimeError("응용 프로그램 폴더 쓰기 권한이 없어 다운로드된 설치 파일을 열었습니다.")

    pid = os.getpid()
    script_path = tmp_dir / "apply_update.sh"
    script_content = f"""#!/bin/bash
PID={pid}
while kill -0 "$PID" 2>/dev/null; do
  sleep 0.2
done
rm -rf "{target_app}"
mv "{staged_app}" "{target_app}"
xattr -dr com.apple.quarantine "{target_app}" 2>/dev/null || true
open -n "{target_app}"
rm -rf "{tmp_dir}"
"""
    script_path.write_text(script_content, encoding="utf-8")
    os.chmod(script_path, 0o755)
    _set_status("applying", 100, "업데이트 적용 후 재시작 중...")
    subprocess.Popen(["/bin/bash", str(script_path)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Timer(0.5, lambda: os._exit(0)).start()


def _apply_windows_update(asset_path: Path, tmp_dir: Path) -> None:
    target_exe = Path(sys.executable).resolve()
    if not os.access(target_exe.parent, os.W_OK):
        subprocess.Popen(["explorer.exe", "/select,", str(asset_path)])
        raise RuntimeError("설치 폴더 쓰기 권한이 없어 다운로드 폴더를 열었습니다.")

    pid = os.getpid()
    bat_path = tmp_dir / "apply_update.bat"
    bat_content = f"""@echo off
setlocal
set "PID={pid}"
set "SRC={asset_path}"
set "DST={target_exe}"

:waitloop
tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
if not errorlevel 1 (
  ping 127.0.0.1 -n 2 >NUL
  goto waitloop
)

set /a tries=0
:moveloop
set /a tries+=1
move /Y "%SRC%" "%DST%" >NUL 2>&1
if errorlevel 1 (
  if %tries% LSS 15 (
    ping 127.0.0.1 -n 2 >NUL
    goto moveloop
  )
)
start "" "%DST%"
rmdir /S /Q "{tmp_dir}" >NUL 2>&1
"""
    bat_path.write_text(bat_content, encoding="utf-8")
    _set_status("applying", 100, "업데이트 적용 후 재시작 중...")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    subprocess.Popen(["cmd.exe", "/c", str(bat_path)], creationflags=flags, close_fds=True)
    threading.Timer(0.5, lambda: os._exit(0)).start()


def start_update() -> Dict[str, Any]:
    """Start downloading and applying the latest release update."""
    with _CACHE_LOCK:
        if _UPDATE_STATUS["state"] in ("downloading", "applying"):
            return dict(_UPDATE_STATUS)

    info = check_for_update(force=True)
    if not info.get("update_available"):
        _set_status("done", 100, "이미 최신 버전입니다.")
        return get_update_status()

    if not info.get("can_auto_update"):
        url = info.get("release_url") or f"https://github.com/{GITHUB_REPO}/releases/latest"
        webbrowser.open(url)
        _set_status("done", 100, "릴리즈 페이지를 열었습니다.")
        return get_update_status()

    asset_url = info["asset_url"]
    asset_name = info["asset_name"] or ("TokenChecker-macOS.dmg" if platform.system() == "Darwin" else "TokenChecker-Windows.exe")
    _set_status("downloading", 0, "업데이트 다운로드 준비 중...")

    def _worker():
        tmp_dir = Path(tempfile.mkdtemp(prefix="tokenchecker_upd_"))
        try:
            dest_path = tmp_dir / asset_name
            _download_file(asset_url, dest_path)
            if platform.system() == "Darwin":
                _apply_macos_update(dest_path, tmp_dir)
            elif platform.system() == "Windows":
                _apply_windows_update(dest_path, tmp_dir)
            else:
                webbrowser.open(info["release_url"])
                _set_status("done", 100, "릴리즈 페이지를 열었습니다.")
        except Exception as e:
            logging.error(f"Auto-update failed: {e}")
            _set_status("error", 0, f"업데이트 실패: {e}")
            shutil.rmtree(tmp_dir, ignore_errors=True)

    threading.Thread(target=_worker, daemon=True).start()
    return get_update_status()
