# Tasks Bridge

MCP server that exposes **Google Tasks** to AI tools (ChatGPT, Cursor) through a normalized tool layer.

## Who is this for?

This is a **single-user personal bridge**: one Google account, one MCP server, one set of OAuth credentials. It is designed for individuals who want ChatGPT or Cursor to read and manage their own Google Tasks.

If you fork or deploy this project, you need **your own** [Google Cloud OAuth client](docs/google-oauth.md). Do not share `credentials.json`, `token.json`, or refresh tokens.

## Features

- **10 MCP tools** — read lists/tasks, search, create, update, complete, move
- **Local dev** — HTTP on `127.0.0.1:8000/mcp`, optional OpenAI tunnel for ChatGPT
- **Production** — deploy to [Railway](docs/railway.md) with static bearer for Inspector, curl, and compatible clients (**not** ChatGPT direct HTTPS)
- **Diagnostics** — `get_bridge_diagnostics` for schema/version verification

### Client access paths

| Path | Status | Works with |
|---|---|---|
| **ChatGPT + OpenAI tunnel** | **Works now** | ChatGPT via [OpenAI Secure MCP Tunnel](docs/chatgpt-tunnel.md) → `localhost:8000/mcp` — **the current ChatGPT-compatible path** |
| **Railway + static bearer** (`MCP_AUTH_MODE=static`) | **Works now** | MCP Inspector (Custom Header), curl, security scanners, compatible custom MCP clients — **not** ChatGPT |
| **Railway + OAuth** (`MCP_AUTH_MODE=oauth`) | **Required for direct ChatGPT → Railway** | ChatGPT over public HTTPS — exploratory; external IdP preferred. See [mcp-oauth-design.md](docs/mcp-oauth-design.md) |

**ChatGPT cannot use Railway static bearer.** The ChatGPT connector UI does not accept `MCP_API_TOKEN`. For ChatGPT today, use the **OpenAI tunnel to localhost**. Static bearer on Railway is for Inspector, curl, scanners, and other clients that can send `Authorization: Bearer …`.

Inbound auth uses exactly one mode at a time: `none` (local default), `static` (production default; requires `MCP_API_TOKEN` everywhere), or `oauth` (stub). See `bridge/auth/` and [docs/railway.md](docs/railway.md).

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp credentials.json.example credentials.json   # see docs/google-oauth.md
python test_task_services.py "General"         # browser OAuth once → token.json

python mcp_server.py
```

See [docs/local-dev.md](docs/local-dev.md) for Cursor, ChatGPT tunnel, and `start_tasks_bridge.sh`.

## Local vs Railway

**One Python app (`mcp_server.py`), two launch paths.** Local dev does **not** use Docker — you run natively in `.venv`. Docker is only for Railway production.

### Local (your Mac)

Default inbound auth: **`none`** (no bearer on `/mcp`). Set `MCP_AUTH_MODE=static` and `MCP_API_TOKEN` in `.env` to exercise bearer locally (Inspector Custom Header, curl). **Do not use `static` with the ChatGPT tunnel** — see [docs/local-dev.md](docs/local-dev.md).

```
Cursor        →  http://127.0.0.1:8000/mcp          (none — no bearer)
MCP Inspector →  http://127.0.0.1:8000/mcp          (none, or bearer if static mode)
ChatGPT       →  OpenAI tunnel ← tunnel-client ← localhost:8000/mcp   (tunnel — not Railway)
                              ↓
                    mcp_server.py  →  bridge/ + services/tasks/  →  Google Tasks API
```

| Concern | Local approach |
|---|---|
| **How you run it** | `./start_tasks_bridge.sh` or `python mcp_server.py` |
| **Config** | Default — `deployment_mode()` returns `local` |
| **Bind address** | `127.0.0.1:8000` |
| **Inbound MCP auth** | `none` (default) — or `static` + `MCP_API_TOKEN` to test bearer |
| **Google OAuth** | `credentials.json` + browser flow → `token.json` on disk |
| **ChatGPT access** | **Tunnel** → localhost ([client access table](#client-access-paths)) |
| **Orchestration** | macOS: `./start_tasks_bridge.sh` (3 compact Terminal windows). Elsewhere: `--http` + `--tunnel` |

Daily commands:

```bash
./start_tasks_bridge.sh --status    # what's running
./start_tasks_bridge.sh             # macOS: 3 compact Terminal windows (default)
./start_tasks_bridge.sh --foreground # MCP + tunnel in this terminal
./start_tasks_bridge.sh --http      # MCP only (Cursor / any OS — use separate tabs)
./start_tasks_bridge.sh --tunnel    # tunnel only (second tab, after MCP is up)
./start_tasks_bridge.sh --stop
```

**Platform note:** On **macOS**, the default opens three compact Terminal windows (MCP, tunnel, Inspector). In **Cursor** or on **Linux**, use **`--http`** and **`--tunnel`** in separate terminal tabs. See [docs/local-dev.md](docs/local-dev.md).

### Railway (production)

Production default inbound auth: **`static`** + **`MCP_API_TOKEN`**. That protects Railway `/mcp` for bearer-capable clients. **ChatGPT does not connect to Railway with static bearer** — use the [OpenAI tunnel](#client-access-paths) locally, or OAuth on Railway when available.

```
GitHub  →  Railway  →  https://<app>.up.railway.app/mcp
                              ↓
     static bearer — Inspector / curl / scanners / compatible clients (not ChatGPT)
                              ↓
              GOOGLE_* env vars  →  Google Tasks API

ChatGPT (today)  →  OpenAI tunnel  ←  tunnel-client  ←  localhost:8000/mcp
                     (not Railway HTTPS; static bearer is not accepted by ChatGPT UI)
```

| Concern | Production approach |
|---|---|
| **How you run it** | Railway builds and runs the `Dockerfile` on deploy |
| **Config** | Auto — `RAILWAY_*` env sets `deployment_mode()` to `production` |
| **Bind address** | `0.0.0.0:$PORT` |
| **Inbound MCP auth** | `static` + `MCP_API_TOKEN` — 401 + `WWW-Authenticate: Bearer` without token |
| **Google OAuth** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` (no browser) |
| **ChatGPT access** | **OpenAI tunnel** → localhost ([client access table](#client-access-paths)) | **Not static bearer** — OAuth required for direct Railway; tunnel on Mac today |
| **Rate limits** | Per-process, IP-keyed — proxy-sensitive on Railway ([docs/railway.md](docs/railway.md)) |
| **Health check** | Railway hits `/health` (`railway.toml`) |

### What stays local-only

These are **not deployed** to Railway:

- `start_tasks_bridge.sh` — local process orchestration
- `tunnel-client` — OpenAI Secure MCP Tunnel binary
- MCP Inspector — dev debugging UI
- `credentials.json` / `token.json` — replaced by Railway env vars in production

`bridge.config` picks deployment behavior from environment variables. You never need to run Docker locally unless you explicitly want to test the production image.

## Deploy (Railway)

Bearer-protected HTTPS for **Inspector, curl, scanners, and compatible MCP clients** — **not** ChatGPT. ChatGPT uses the **OpenAI tunnel to localhost** today; direct ChatGPT → Railway requires **OAuth** (exploratory).

```
GitHub → Railway → https://your-app.up.railway.app/mcp  (Authorization: Bearer MCP_API_TOKEN)
```

Set `MCP_API_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` in Railway. See [docs/railway.md](docs/railway.md). For ChatGPT + Railway possibilities (uncertain), see **[docs/mcp-oauth-design.md](docs/mcp-oauth-design.md)**.

## Project layout

Bridge host (shared MCP infrastructure) and pluggable services:

```
bridge/
  auth/          inbound MCP auth (none | static | oauth)
  config/        deployment settings
  diagnostics/   version, schema hash
  logging/       MCP discovery logging
  transport/     HTTP hardening, DNS rebinding settings

services/
  tasks/         Google Tasks tools (today's MCP surface)

mcp_server.py    entry point — wires bridge + services.tasks
start_tasks_bridge.sh   local orchestration (not deployed to Railway)
```

| Path | Purpose |
|---|---|
| `mcp_server.py` | Entry point; `create_server(auth_provider)` |
| `bridge/` | Shared bridge host (auth, config, diagnostics, transport, logging) |
| `services/tasks/` | Google Tasks MCP tools and API adapters |
| `start_tasks_bridge.sh` | Local orchestration — macOS default: 3 compact Terminal windows |

## Google OAuth

Each user creates a Desktop OAuth client in Google Cloud Console, enables the Tasks API, and runs the local browser flow once. Apps in **Testing** mode work for personal use (test users only). See [docs/google-oauth.md](docs/google-oauth.md).

## Secrets (never commit)

- `credentials.json`, `token.json`, `.env`
- Railway: use platform secret variables

Copy `.env.example` and `credentials.json.example` as templates. See [SECURITY.md](SECURITY.md).

## Status

Operational details: [PROJECT_STATUS.md](PROJECT_STATUS.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and doc fixes welcome.

## License

[MIT License](LICENSE) — Copyright (c) 2026 Adam Weinrich
