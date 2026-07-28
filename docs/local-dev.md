# Local development

Tasks Bridge runs locally as a FastMCP HTTP server on port 8000. Default inbound auth is **`none`** (no bearer). See the [client access paths](../README.md#client-access-paths) in README — ChatGPT uses the tunnel; Cursor and Inspector hit localhost directly.

## Architecture (local)

Matches README client access table — **ChatGPT + local tunnel** (works now):

```
Cursor        →  http://127.0.0.1:8000/mcp     (none — no bearer by default)
MCP Inspector →  http://127.0.0.1:8000/mcp     (none, or bearer if MCP_AUTH_MODE=static)
ChatGPT       →  OpenAI tunnel ← tunnel-client ← localhost:8000/mcp
                              ↓
                    bridge/ + services/tasks/  →  Google Tasks API
```

Set `MCP_AUTH_MODE=static` and `MCP_API_TOKEN` in `.env` to test bearer auth locally (required token in that mode). **Leave auth at `none` (default) if you use the ChatGPT tunnel** — `tunnel-client` does not send a bearer header.

## `.env` file

Copy `.env.example` to `.env`. The startup script and macOS MCP Server Terminal window **source `.env` on launch** so the server sees your variables.

Comments use `#` (full-line or inline with whitespace before `#`):

```bash
# Inbound MCP auth — use none for ChatGPT tunnel; static to test Railway-style bearer
MCP_AUTH_MODE=static
MCP_API_TOKEN=your-secret-here

# ChatGPT tunnel
CONTROL_PLANE_API_KEY=...
CONTROL_PLANE_TUNNEL_ID=...
TUNNEL_CLIENT_PROFILE=tasks-bridge
```

| Variable | Local default | Notes |
|---|---|---|
| `MCP_AUTH_MODE` | `none` | `static` requires `MCP_API_TOKEN`; `oauth` is a stub |
| `MCP_API_TOKEN` | unset | Required when mode is `static` |

Generate a token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Test static bearer with MCP Inspector

1. Set `MCP_AUTH_MODE=static` and `MCP_API_TOKEN` in `.env`.
2. Restart the MCP server (`./start_tasks_bridge.sh --stop` then `./start_tasks_bridge.sh`).
3. Open Inspector (`http://127.0.0.1:6274` when started via `--windows`).
4. **Server Entry** → expand **Authentication** → **Custom Headers** → **+ Add**:
   - **Header name:** `Authorization`
   - **Header value:** `Bearer <same value as MCP_API_TOKEN>`
5. Do **not** fill in the OAuth 2.0 section — that is for OAuth servers, not static bearer.
6. Connect to `http://127.0.0.1:8000/mcp`.

Without the header you should get **401** with `WWW-Authenticate: Bearer realm="Tasks Bridge MCP"`.

### Static bearer vs ChatGPT tunnel

| Local setup | ChatGPT tunnel | Inspector / curl |
|---|---|---|
| `MCP_AUTH_MODE=none` (default) | Works | Works without bearer |
| `MCP_AUTH_MODE=static` + token | **Broken** (tunnel has no bearer) | Works with `Authorization` header |

Use `none` for daily ChatGPT + Cursor dev. Use `static` only when testing the same auth Railway uses.

## Platform support

The **MCP server** (`mcp_server.py`), Python tests, and Cursor integration are **cross-platform**.

| Mode | Platform | What it does |
|---|---|---|
| `python mcp_server.py` | Any | MCP server only |
| `./start_tasks_bridge.sh --http` | Any* | MCP server in current terminal |
| `./start_tasks_bridge.sh --tunnel` | Any* | Tunnel only (MCP must already be running) |
| `./start_tasks_bridge.sh` (default) | **macOS** | Three compact Terminal windows (MCP, tunnel, Inspector) |
| `./start_tasks_bridge.sh` (default) | Linux / other | MCP foreground + tunnel in one terminal |
| `./start_tasks_bridge.sh --foreground` | Any* | MCP + tunnel in this terminal (old macOS default) |
| `./start_tasks_bridge.sh --windows` | **macOS only** | Same as default — three compact Terminal windows |
| `./start_tasks_bridge.sh --stop` | Any* | Kill processes; close Terminal windows opened by `--windows` |

\* Requires bash, Python 3.11+, and `lsof` (common on macOS/Linux).

### Why not one window with native tabs?

Automating Terminal.app tabs via AppleScript proved **unreliable** (hangs, system lockups). **tmux** works but requires obscure key chords and breaks in Cursor’s integrated terminal. For discoverability, we use **separate named windows** on macOS instead.

### macOS `--windows` (Terminal.app)

Opens three compact Terminal windows (default **440×260**, stacked vertically) with clear titles — switch with **Cmd+`** or the **Window** menu:

```bash
./start_tasks_bridge.sh
```

Resize defaults in `.env`:

```bash
TASKS_BRIDGE_WINDOW_WIDTH=440
TASKS_BRIDGE_WINDOW_HEIGHT=260
TASKS_BRIDGE_WINDOW_X=20
TASKS_BRIDGE_WINDOW_Y=40
TASKS_BRIDGE_WINDOW_GAP=8
```

| Window title | Service |
|---|---|
| Tasks Bridge — MCP Server | `python mcp_server.py` (sources `.env` first) |
| Tasks Bridge — Tunnel | `tunnel-client` |
| Tasks Bridge — Inspector | MCP Inspector UI |

Skip Inspector: `./start_tasks_bridge.sh --windows --no-inspector`

Stop everything: `./start_tasks_bridge.sh --stop`

`--stop` kills MCP, tunnel, and Inspector **first**, then closes Tasks Bridge Terminal windows (by saved window id and by tab title). That order avoids most “terminate running processes?” prompts. If Terminal still asks, you can disable the global prompt:

```bash
defaults write com.apple.Terminal ShellNeverPromptsOnClose -bool true
```

### `--status` and tunnel “idle”

`./start_tasks_bridge.sh --status` probes MCP with a real `initialize` request (includes the bearer token when `MCP_AUTH_MODE=static`). For the tunnel, a running `tunnel-client` with a healthy MCP server reports **UP** even when idle — the tunnel connects **on demand** when ChatGPT calls, so an idle tunnel is normal, not STALE.


Open **separate terminal tabs** in Cursor (or any terminal emulator):

**Tab 1 — MCP:**
```bash
./start_tasks_bridge.sh --http
```

**Tab 2 — tunnel** (after MCP is up):
```bash
./start_tasks_bridge.sh --tunnel
```

**Tab 3 — Inspector** (optional):
```bash
npx -y @modelcontextprotocol/inspector --transport http --server-url http://127.0.0.1:8000/mcp
```

No special keys, no tmux, works everywhere.

## One-time setup

```bash
git clone <your-repo-url>
cd Tasks_AI_Bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Google OAuth (local)

See [google-oauth.md](google-oauth.md) for full setup (consent screen, Testing mode limits, Railway seeding).

Quick path:

1. Create a **Desktop app** OAuth client in [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Enable the **Google Tasks API** for your project.
3. Download client JSON and save as `credentials.json` (see `credentials.json.example`).
4. Run a smoke test — a browser window opens on first use:

```bash
python test_task_services.py "General"
```

This creates `token.json` locally. **Never commit** `credentials.json` or `token.json`.

### ChatGPT tunnel (optional)

Copy `.env.example` to `.env` and configure OpenAI tunnel credentials. See [chatgpt-tunnel.md](chatgpt-tunnel.md).

## Daily use

**macOS (Terminal.app):**
```bash
./start_tasks_bridge.sh --status
./start_tasks_bridge.sh --windows
./start_tasks_bridge.sh --stop
```

**Cursor / cross-platform:**
```bash
./start_tasks_bridge.sh --status
./start_tasks_bridge.sh --http      # tab 1
./start_tasks_bridge.sh --tunnel    # tab 2
./start_tasks_bridge.sh --stop
```

Or run the server directly:

```bash
python mcp_server.py
```

## Cursor

`.cursor/mcp.json` points at `http://127.0.0.1:8000/mcp`. Restart the MCP server after code changes.

## Tests

```bash
python test_bridge_diagnostics.py   # no Google API
python test_config.py               # config only
python test_task_services.py "General"
python test_write_task_services.py "General"
```

## Production

Local scripts (`start_tasks_bridge.sh`, `tunnel-client`, Inspector) are **not used on Railway**. See [railway.md](railway.md).
