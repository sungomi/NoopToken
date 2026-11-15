#!/bin/zsh
set -e
cd "$(dirname "$0")"

# 1. 가상환경(.venv) 자동 구성 (최초 1회)
if [ ! -x ".venv/bin/python" ]; then
  echo "📦 최초 실행: Python 가상환경 및 필수 패키지를 설치합니다..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install -r requirements.txt
  elif [ -x "/opt/homebrew/bin/uv" ]; then
    /opt/homebrew/bin/uv venv .venv
    /opt/homebrew/bin/uv pip install -r requirements.txt
  else
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
  fi
fi

# 2. 위젯 실행
exec .venv/bin/python widget.py "$@"
