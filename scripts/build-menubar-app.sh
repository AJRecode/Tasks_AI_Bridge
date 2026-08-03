#!/usr/bin/env bash
# Build Tasks Bridge.app for the macOS menu bar (no py2app — uses repo .venv).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MENUBAR_DIR="$ROOT/macos/menubar"
VENV="$ROOT/.venv"
DIST="$MENUBAR_DIR/dist"
APP="$DIST/Tasks Bridge.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
LAUNCHER="$MACOS/TasksBridge"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Tasks Bridge menu bar app is macOS only."
  exit 1
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Installing menu bar dependencies into .venv..."
"$VENV/bin/pip" install -q -r "$MENUBAR_DIR/requirements.txt"

echo "Building Tasks Bridge.app..."
rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES"

printf '%s' "$ROOT" >"$RESOURCES/project_path"
echo "$ROOT" >"$MENUBAR_DIR/.project_path"

cat >"$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>TasksBridge</string>
  <key>CFBundleIdentifier</key>
  <string>com.tasksbridge.menubar</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Tasks Bridge</string>
  <key>CFBundleDisplayName</key>
  <string>Tasks Bridge</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

cat >"$LAUNCHER" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RESOURCES="$APP_DIR/Contents/Resources"
PROJECT_DIR="$(tr -d '\r\n' < "$RESOURCES/project_path")"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
MENUBAR_PY="$PROJECT_DIR/macos/menubar/tasks_bridge_menubar.py"

alert() {
  /usr/bin/osascript -e "display alert \"Tasks Bridge\" message \"$1\" as critical" >/dev/null 2>&1 || true
}

if [[ ! -d "$PROJECT_DIR" ]]; then
  alert "Project directory not found: $PROJECT_DIR"
  exit 1
fi

if [[ ! -x "$VENV_PY" ]]; then
  alert "Missing Python venv at $PROJECT_DIR/.venv — run: python3 -m venv .venv && pip install -r requirements.txt -r macos/menubar/requirements.txt"
  exit 1
fi

if [[ ! -f "$MENUBAR_PY" ]]; then
  alert "Missing menu bar script: $MENUBAR_PY"
  exit 1
fi

export TASKS_BRIDGE_PROJECT_DIR="$PROJECT_DIR"
exec "$VENV_PY" "$MENUBAR_PY"
LAUNCHER

chmod +x "$LAUNCHER"

echo
echo "Built: $APP"
echo "Uses venv: $VENV/bin/python"
echo "Project:  $ROOT"
echo
echo "Try it:"
echo "  open \"$APP\""
echo
echo "Install to Applications (optional):"
echo "  cp -R \"$APP\" /Applications/"
echo
echo "Add to Login Items: System Settings → General → Login Items → add Tasks Bridge.app"
echo
echo "Note: If you move the repo, re-run ./scripts/build-menubar-app.sh to refresh the embedded path."
echo "The menu bar app does not stop bridge services when you quit it — use Stop Bridge first."
