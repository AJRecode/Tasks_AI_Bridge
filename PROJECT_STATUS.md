# Project Status

* **Last updated:** July 27, 2026 (OAuth doc: exploratory, external IdP first)
* **Server version:** `1.6.0` (`bridge_diagnostics.py`)
* **License:** MIT
* **Deployment modes:** `local` (default) | `production` (Railway via env)
* **Inbound auth modes:** `none` (local) | `static` (Railway bearer) | `oauth` (exploratory stub)

## Summary

Tasks Bridge exposes **Google Tasks** to AI tools (ChatGPT, Cursor) through an MCP server. One Python codebase runs locally (native `.venv`) or on Railway (Docker). Inbound MCP auth is selected via `MCP_AUTH_MODE`: **none** for local dev, **static** bearer for Railway scripts/clients, **oauth** exploratory stub for a possible ChatGPT + HTTPS path (external IdP preferred — not a custom auth server). **ChatGPT today** uses the OpenAI Secure MCP Tunnel to localhost.

## Architecture

### Local

```
ChatGPT  →  OpenAI tunnel  ←  tunnel-client  ←  http://127.0.0.1:8000/mcp  ←  mcp_server.py
Cursor   →  http://127.0.0.1:8000/mcp
Dev      →  MCP Inspector → http://127.0.0.1:8000/mcp
                              ↓
                    task_services.py  →  google_tasks.py / google_auth.py  →  Google Tasks API
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
| Inbound auth | `auth/` — `none` / `static` / `oauth` (stub); bearer before handler |
| HTTP hardening | `http_security.py` — rate/size limits, error shield (production) |
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

| File | Role |
|---|---|
| `mcp_server.py` | `create_server(auth_provider)` — FastMCP, `/health`, MCP tools |
| `auth/` | Inbound auth modes: `none`, `static_bearer`, `oauth` (stub), `factory` |
| `http_security.py` | Rate limits, request-size limits, error shield (no auth) |
| `config.py` | Local vs production settings, `MCP_AUTH_MODE` |
| `google_auth.py` | File OAuth (local) or env vars (Railway) |
| `start_tasks_bridge.sh` | Local orchestration only |
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

OAuth doc reframed as exploratory: evaluate external IdP (resource server only) before any custom authorization server. Tunnel remains the practical ChatGPT path.

## Next action

No restart needed (docs + error message only). Commit when ready.
