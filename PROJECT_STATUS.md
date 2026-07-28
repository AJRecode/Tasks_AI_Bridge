# Project Status

* **Last updated:** July 27, 2026 (package layout: bridge/ + services/tasks/)
* **Server version:** `1.6.0` (`bridge/diagnostics/`)
* **License:** MIT
* **Deployment modes:** `local` (default) | `production` (Railway via env)
* **Inbound auth modes:** `none` (local) | `static` (Railway bearer) | `oauth` (exploratory stub)

## Summary

Tasks Bridge is an **MCP bridge host** (`bridge/`) with pluggable **services** (Google Tasks today). One Python codebase runs locally (native `.venv`) or on Railway (Docker).

## Architecture

### Local

```
ChatGPT  →  OpenAI tunnel  ←  tunnel-client  ←  http://127.0.0.1:8000/mcp  ←  mcp_server.py
Cursor   →  http://127.0.0.1:8000/mcp
Dev      →  MCP Inspector → http://127.0.0.1:8000/mcp
                              ↓
                    bridge/ (auth, transport, diagnostics)
                    services/tasks/  →  Google Tasks API
```

### Production (Railway)

```
GitHub  →  Railway  →  https://<app>.up.railway.app/mcp  →  curl / Inspector / custom clients (Bearer)
                              ↓
                    google_auth (env vars)  →  Google Tasks API
```

| Mode | Entry | Google auth | Inbound MCP auth | ChatGPT path |
|---|---|---|---|---|
| Local | `python mcp_server.py` / `start_tasks_bridge.sh` | `credentials.json` + `token.json` | `none` (default) | `tunnel-client` → localhost |
| Production | Docker / Railway | `GOOGLE_*` env vars | `static` bearer (default) | **Exploratory** — tunnel today; Railway HTTPS only if IdP spike succeeds |

## MCP tools (10)

`get_bridge_diagnostics`, `get_task_lists`, `get_tasks`, `get_open_tasks`, `search_tasks`, `create_task_list`, `create_task`, `update_task`, `complete_task`, `move_task`.

`get_bridge_diagnostics` includes `auth_mode`.

## Verified working

| Capability | How to verify |
|---|---|
| Config local/production | `python test_config.py` or `pytest test_config.py` |
| Auth mode resolution | `pytest test_auth.py` |
| Diagnostics | `python test_bridge_diagnostics.py` or `pytest test_bridge_diagnostics.py` |
| Google Tasks API (local) | `python test_task_services.py "General"` (requires OAuth files) |
| MCP HTTP + `/health` | `curl http://127.0.0.1:8000/health` |
| Local orchestration | `./start_tasks_bridge.sh --status` (tunnel idle = UP, not STALE) |
| Railway artifacts | `Dockerfile`, `railway.toml`, `/health` route |
| GitHub CI | `.github/workflows/ci.yml` — pytest, pip-audit, bandit on push/PR |
| Inbound auth | `bridge/auth/` — `none` / `static` / `oauth` (stub) |
| HTTP hardening | `bridge/transport/` — rate/size limits, error shield |
| Dependabot | `.github/dependabot.yml` — weekly pip, Docker, Actions updates |

## Runtime status

Run `./start_tasks_bridge.sh --status` for a live snapshot. PIDs and process details are not recorded here (they go stale in git).

## Known issues

* **ChatGPT tool discovery lag** — new MCP tools may appear in Inspector before ChatGPT exposes them. Likely OpenAI registry propagation, not a stale server. See [docs/chatgpt-discovery.md](docs/chatgpt-discovery.md).
* **`oauth_metadata` warnings** — expected until an OAuth path is chosen (tunnel works today).
* **`MCP_AUTH_MODE=oauth`** — fails fast; direction is exploratory ([docs/mcp-oauth-design.md](docs/mcp-oauth-design.md)).
* **`tools/list_changed` not enabled** — optional future enhancement.

## Roadmap

* [ ] First public GitHub release + Railway deploy (`MCP_AUTH_MODE=static`)
* [ ] **Direct Railway → ChatGPT** — exploratory; time-boxed external IdP spike before any code — [docs/mcp-oauth-design.md](docs/mcp-oauth-design.md)
* [ ] ChatGPT continues on OpenAI tunnel unless IdP + ChatGPT handshake succeeds
* [ ] Optional: `tools/list_changed` + stateful HTTP for faster ChatGPT discovery

## Key files

| Path | Role |
|---|---|
| `mcp_server.py` | Entry point — `create_server(auth_provider)` |
| `bridge/auth/` | Inbound auth modes |
| `bridge/config/` | Deployment settings |
| `bridge/diagnostics/` | Version, schema hash |
| `bridge/logging/` | MCP discovery logging |
| `bridge/transport/` | HTTP hardening, transport security |
| `services/tasks/` | Google Tasks MCP tools + API adapters |
| `start_tasks_bridge.sh` | Local orchestration |
| `Dockerfile` / `railway.toml` | Railway production deploy |
| `docs/local-dev.md` | Local setup |
| `docs/railway.md` | Railway deploy |
| `docs/mcp-oauth-design.md` | OAuth exploration for ChatGPT + HTTPS (external IdP first) |
| `docs/chatgpt-tunnel.md` | OpenAI tunnel setup |
| `docs/chatgpt-discovery.md` | Debugging ChatGPT tool discovery |
| `.github/workflows/ci.yml` | CI: unit tests + dependency audit + security scan |
| `.github/dependabot.yml` | Automated dependency update PRs |
| `scripts/check.sh` | Local pre-push gate (mirrors CI) |

## Docs

- [README.md](README.md) — quick start and layout
- [SECURITY.md](SECURITY.md) — secrets policy
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute

## Recent result

Reorganized into **bridge host** (`bridge/`) + **services** (`services/tasks/`). Root shims (`config.py`, `task_services.py`, etc.) remain for compatibility. All 20 unit tests pass.

## Next action

Restart MCP after pull: `./start_tasks_bridge.sh`
