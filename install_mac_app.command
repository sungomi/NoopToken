#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="/Applications/TokenChecker.app"

echo "[TokenChecker] Installing macOS application bundle to $APP_PATH..."
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

if [ -f "$DIR/assets/icon.icns" ]; then
  cp "$DIR/assets/icon.icns" "$APP_PATH/Contents/Resources/icon.icns"
fi

cat > "$APP_PATH/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.sungomi.tokenchecker</string>
    <key>CFBundleName</key>
    <string>TokenChecker</string>
    <key>CFBundleDisplayName</key>
    <string>TokenChecker</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.3.0</string>
    <key>LSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

cat > "$APP_PATH/Contents/MacOS/launcher" <<EOF
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$HOME/.local/bin:\$PATH"
cd "$DIR"
exec "$DIR/run_mac.command"
EOF

chmod +x "$DIR/run_mac.command"
chmod +x "$APP_PATH/Contents/MacOS/launcher"
echo "[OK] Installed '$APP_PATH' successfully!"
open "$APP_PATH"
