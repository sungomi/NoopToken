#!/bin/zsh
set -e
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# 먼저 가상환경 준비
if [ ! -x ".venv/bin/python" ]; then
  echo "📦 필수 패키지를 먼저 설치합니다..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv && uv pip install -r requirements.txt
  elif [ -x "/opt/homebrew/bin/uv" ]; then
    /opt/homebrew/bin/uv venv .venv && /opt/homebrew/bin/uv pip install -r requirements.txt
  else
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  fi
fi

APP_PATH="/Applications/AI Quota Monitor.app"
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

cat > "$APP_PATH/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleIdentifier</key>
  <string>com.sungomi.ai-quota-monitor</string>
  <key>CFBundleName</key>
  <string>AI Quota Monitor</string>
  <key>CFBundleDisplayName</key>
  <string>AI 사용량 모니터</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>LSUIElement</key>
  <false/>
</dict>
</plist>
EOF

cat > "$APP_PATH/Contents/MacOS/launcher" <<EOF
#!/bin/zsh
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/widget.py"
EOF

chmod +x "$APP_PATH/Contents/MacOS/launcher"
echo "✅ '/Applications/AI Quota Monitor.app' 설치 완료! 이제 런치패드나 응용 프로그램 폴더에서 바로 실행할 수 있습니다."
