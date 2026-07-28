# Tasks Bridge

MCP server that exposes **Google Tasks** to AI tools (ChatGPT, Cursor) through a normalized tool layer.

## Who is this for?

This is a **single-user personal bridge**: one Google account, one MCP server, one set of OAuth credentials. It is designed for individuals who want ChatGPT or Cursor to read and manage their own Google Tasks.

If you fork or deploy this project, you need **your own** [Google Cloud OAuth client](docs/google-oauth.md). Do not share `credentials.json`, `token.json`, or refresh tokens.

## Features

- **10 MCP tools** — read lists/tasks, search, create, update, complete, move
- **Local dev** — HTTP on `127.0.0.1:8000/mcp`, optional OpenAI tunnel for ChatGPT
- **Production** — deploy to [Railway](docs/railway.md) with bearer-protected public HTTPS (`MCP_API_TOKEN`)
- **Diagnostics** — `get_bridge_diagnostics` for schema/version verification

> **ChatGPT today:** use the [OpenAI Secure MCP Tunnel](docs/chatgpt-tunnel.md) to localhost — the ChatGPT connector UI does not support static bearer tokens. **Direct Railway → ChatGPT** is **planned** pending [MCP endpoint OAuth](docs/mcp-oauth-design.md). Bearer-protected Railway deployments work now with **curl**, security **scanners**, **MCP Inspector**, and other clients that send `Authorization: Bearer …`.

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

```
Cursor        →  http://127.0.0.1:8000/mcp
MCP Inspector →  http://127.0.0.1:8000/mcp   (dev UI, optional)
ChatGPT       →  OpenAI tunnel ← tunnel-client ← http://127.0.0.1:8000/mcp
                              ↓
                    python mcp_server.py  (in .venv)
                              ↓
                    credentials.json + token.json  →  Google Tasks API
```

| Concern | Local approach |
|---|---|
| **How you run it** | `./start_tasks_bridge.sh` or `python mcp_server.py` |
| **Config** | Default — `config.deployment_mode()` returns `local` |
| **Bind address** | `127.0.0.1:8000` |
| **Google OAuth** | `credentials.json` + browser flow → `token.json` on disk |
| **ChatGPT access** | `tunnel-client` exposes localhost (ChatGPT can't reach `127.0.0.1`) |
| **Orchestration** | macOS: `--windows` (3 Terminal windows). Elsewhere: `--http` + `--tunnel` in separate tabs |

Daily commands:

```bash
./start_tasks_bridge.sh --status    # what's running
./start_tasks_bridge.sh --windows   # macOS: 3 named Terminal.app windows
./start_tasks_bridge.sh --http      # MCP only (Cursor / any OS — use separate tabs)
./start_tasks_bridge.sh --tunnel    # tunnel only (second tab, after MCP is up)
./start_tasks_bridge.sh --stop
```

**Platform note:** **`--windows`** opens three separate Terminal.app windows on macOS (no tmux, no key chords). In **Cursor** or on **Linux**, use **`--http`** and **`--tunnel`** in separate terminal tabs. See [docs/local-dev.md](docs/local-dev.md).

### Railway (production)

```
GitHub  →  Railway (Dockerfile)  →  https://<app>.up.railway.app/mcp  →  curl / Inspector / custom clients
                                              ↓                              (Bearer MCP_API_TOKEN)
                                    GOOGLE_* env vars  →  Google Tasks API

ChatGPT (today)  →  OpenAI tunnel  ←  tunnel-client  ←  localhost:8000/mcp   (see mcp-oauth-design.md for Railway HTTPS)
```

| Concern | Production approach |
|---|---|
| **How you run it** | Railway builds and runs the `Dockerfile` on deploy |
| **Config** | Auto — `RAILWAY_*` env sets `deployment_mode()` to `production` |
| **Bind address** | `0.0.0.0:$PORT` |
| **Google OAuth** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` (no browser) |
| **Inbound MCP auth** | `MCP_API_TOKEN` bearer on `/mcp` — works with curl, scanners, Inspector, compatible custom clients |
| **ChatGPT access** | **Tunnel to localhost today** — direct Railway HTTPS is **planned** ([MCP OAuth design](docs/mcp-oauth-design.md)) |
| **Health check** | Railway hits `/health` (`railway.toml`) |

### What stays local-only

These are **not deployed** to Railway:

- `start_tasks_bridge.sh` — local process orchestration
- `tunnel-client` — OpenAI Secure MCP Tunnel binary
- MCP Inspector — dev debugging UI
- `credentials.json` / `token.json` — replaced by Railway env vars in production

`config.py` picks the right behavior automatically from environment variables. You never need to run Docker locally unless you explicitly want to test the production image.

## Deploy (Railway)

Bearer-protected HTTPS for curl, scanners, Inspector, and compatible MCP clients — **not** ChatGPT direct HTTPS until MCP OAuth is built.

```
GitHub → Railway → https://your-app.up.railway.app/mcp  (Authorization: Bearer MCP_API_TOKEN)
```

Set `MCP_API_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` in Railway. See [docs/railway.md](docs/railway.md). For the ChatGPT + Railway roadmap, see **[docs/mcp-oauth-design.md](docs/mcp-oauth-design.md)**.

## Project layout

| File | Purpose |
|---|---|
| `mcp_server.py` | FastMCP HTTP/stdio entry point |
| `task_services.py` | Business logic and list-name resolution |
| `google_tasks.py` | Google Tasks API adapter |
| `google_auth.py` | OAuth (local files or env vars) |
| `config.py` | Local vs production settings |
| `bridge_diagnostics.py` | Version, schema hash, discovery logging |
| `start_tasks_bridge.sh` | Local orchestration — `--windows` on macOS; `--http`/`--tunnel` elsewhere; not used on Railway |

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
