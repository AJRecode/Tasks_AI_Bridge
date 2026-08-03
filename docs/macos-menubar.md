# macOS menu bar app

One-click control for Tasks Bridge from the menu bar — without Automator, Shortcuts, or fragile shell wrappers.

The app calls your existing `start_tasks_bridge.sh` (same behavior as running it in Terminal: three compact windows for MCP, tunnel, and Inspector).

## Why this instead of Automator?

| Approach | Typical pain |
|---|---|
| Automator / Shortcuts “Run Shell Script” | Wrong cwd, no `.env`, Terminal prompts, hard to stop cleanly |
| `.command` files in Dock | Opens Terminal every time; easy to lose track of processes |
| **Menu bar app (this)** | Fixed project path, Start / Stop / Restart / Status, notifications |

## Quick try (no build)

```bash
cd Tasks_AI_Bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r macos/menubar/requirements.txt
python macos/menubar/tasks_bridge_menubar.py
```

A **TB / TB ✓ / TB ◐** label appears in the menu bar (top-right). Click it for the menu.

## Build `Tasks Bridge.app`

Uses a lightweight `.app` bundle that runs your repo's `.venv` (no py2app — avoids pyenv/libpython bundling issues):

```bash
./scripts/build-menubar-app.sh
open "macos/menubar/dist/Tasks Bridge.app"
```

Optional install:

```bash
cp -R "macos/menubar/dist/Tasks Bridge.app" /Applications/
```

**Login Items:** System Settings → General → Login Items → add **Tasks Bridge.app** so the menu bar icon appears at sign-in.

The app is **menu bar only** (no Dock icon). Quitting the menu bar app does **not** stop MCP/tunnel — use **Stop Bridge** first if you want everything down.

## Menu actions

| Item | Action |
|---|---|
| **Start Bridge** | `./start_tasks_bridge.sh` (3 Terminal windows) |
| **Stop Bridge** | `./start_tasks_bridge.sh --stop` |
| **Restart Bridge** | stop, then start |
| **Show Status** | Notification with MCP / tunnel / Inspector state |
| **Open Inspector** | Opens `http://127.0.0.1:6274` |
| **Copy MCP URL** | Copies `http://127.0.0.1:8000/mcp` |

The label refreshes every 30 seconds:

- **TB ✓** — MCP up (and tunnel up or N/A)
- **TB ◐** — MCP up but tunnel/inspector needs attention
- **TB** — MCP not running

### Menu bar overflow (MacBook notch)

If you do not see **TB**, macOS may have hidden it in the menu bar overflow (**◀** or **…** at the right edge of the menu bar). Click that control, or hold **⌘** and drag menu bar icons to reorder and keep **TB** visible.

## ChatGPT vs static bearer

The menu bar app only starts/stops services. If you use `MCP_AUTH_MODE=static` in `.env`, the **ChatGPT tunnel will not work** (tunnel does not send bearer). Use `none` for daily ChatGPT; use `static` only when testing Railway-style auth in Inspector.

## Alternatives

- **Terminal + `./start_tasks_bridge.sh`** — same backend, more visibility in log windows
- **SwiftBar** — if you prefer a shell-script plugin instead of a small Python app

## Files

```
macos/menubar/tasks_bridge_menubar.py   # menu bar logic
scripts/build-menubar-app.sh            # one-command .app build (no py2app)
```

Built apps embed the repo path in `Contents/Resources/project_path` at build time. Re-run the build script if you move the project directory. The app uses your repo `.venv` (install `macos/menubar/requirements.txt` for `rumps`).
