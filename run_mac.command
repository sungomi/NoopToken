#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -x ".venv/bin/python" ]; then
  echo "[AI Monitor v1.0] Setting up Python virtual environment (.venv)..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install -r requirements.txt
  else
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -r requirements.txt -q
  fi
fi

exec .venv/bin/python widget.py "$@"
