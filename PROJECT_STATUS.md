# Project Status

* **Last updated:** August 28, 2026 11:30 ET (pip-audit CVE pin bump: cryptography 50.0.1, PyJWT 2.13.0)
* **Server version:** `1.7.0` (`bridge/diagnostics/` — unchanged; dep-only fix)
* **License:** MIT
* **Deployment modes:** `local` (default) | `production` (Railway via env)
* **Inbound auth modes:** `none` (local) | `static` (Railway bearer) | `oauth` (WorkOS/AuthKit resource server)

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
ChatGPT (after oauth handshake) → https://<app>.up.railway.app/mcp  (WorkOS JWT)
curl / Inspector                → same URL with static bearer (MCP_AUTH_MODE=static)
                              ↓
                    google_auth (env vars)  →  Google Tasks API
```

| Mode | Entry | Google auth | Inbound MCP auth | ChatGPT path |
|---|---|---|---|---|
| Local | `python mcp_server.py` / `start_tasks_bridge.sh` | `credentials.json` + `token.json` | `none` (default) | `tunnel-client` → localhost |
| Production `static` | Docker / Railway | `GOOGLE_*` env vars | `MCP_API_TOKEN` bearer | Not ChatGPT — use tunnel |
| Production `oauth` | Docker / Railway | `GOOGLE_*` env vars | WorkOS JWT + email allowlist | New ChatGPT plugin, **OAuth** |

## MCP tools (10)

`get_bridge_diagnostics`, `get_task_lists`, `get_tasks`, `get_open_tasks`, `search_tasks`, `create_task_list`, `create_task`, `update_task`, `complete_task`, `move_task`.

`get_bridge_diagnostics` includes `auth_mode`.

## Verified working

| Capability | How to verify |
|---|---|
| Config local/production | `python test_config.py` or `pytest test_config.py` |
| Auth mode resolution | `pytest test_auth.py` |
| Static bearer ASGI | `pytest test_static_bearer.py` |
| HTTP auth integration | `pytest test_http_integration.py` |
| WorkOS oauth verifier + 401 metadata | `pytest test_oauth.py test_http_integration.py` (this session) |
| Task tools (mocked Google API) | `pytest test_task_tools_mocked.py` |
| Diagnostics | `python test_bridge_diagnostics.py` or `pytest test_bridge_diagnostics.py` |
| Google Tasks API (local) | `python test_task_services.py "General"` (requires OAuth files) |
| MCP HTTP + `/health` | `curl http://127.0.0.1:8000/health` |
| Local orchestration | `./start_tasks_bridge.sh --status` (tunnel idle = UP, not STALE) |
| macOS menu bar app | `./scripts/build-menubar-app.sh` → [docs/macos-menubar.md](docs/macos-menubar.md) |
| Railway `/health` | `https://tasksaibridge-production.up.railway.app/health` (static, 2026-08-28) |
| GitHub CI | `.github/workflows/ci.yml` — pytest, pip-audit, bandit on push/PR |
| Inbound auth | `bridge/auth/` — `static` requires `MCP_API_TOKEN`; `oauth` requires WorkOS env vars |
| HTTP hardening | `bridge/transport/` — per-process rate limits (proxy-sensitive), size limits |
| Dependabot | `.github/dependabot.yml` — weekly pip, Docker, Actions updates |

ChatGPT → Railway OAuth handshake is **not** verified until a new ChatGPT plugin completes AuthKit login against the oauth deploy.

## Runtime status

Run `./start_tasks_bridge.sh --status` for a live snapshot. PIDs and process details are not recorded here (they go stale in git).

## Known issues

* **ChatGPT tool discovery lag** — new MCP tools may appear in Inspector before ChatGPT exposes them. See [docs/chatgpt-discovery.md](docs/chatgpt-discovery.md).
* **ChatGPT plugin UI** — OAuth / No auth / Mixed only (no bearer Token). Direct Railway ChatGPT requires `MCP_AUTH_MODE=oauth`.
* **WorkOS “Set as default”** on a single resource indicator may be hidden; ChatGPT should still send `resource=` the `/mcp` URL.
* **`tools/list_changed` not enabled** — optional future enhancement.
* **ChatGPT tunnel + `MCP_AUTH_MODE=static`** — incompatible; tunnel does not send bearer. Use `none` locally for ChatGPT.
* **cryptography >= 49 dropped x86_64 macOS wheels.** CI (Ubuntu) and Railway (Linux) install `cryptography==50.0.1` fine. A local Rosetta / Intel `python` cannot `pip install` that pin from wheels; use native arm64 Python 3.11.

## Roadmap

* [ ] Push oauth code, set Railway `MCP_AUTH_MODE=oauth` + WorkOS vars, confirm `/mcp` 401 `resource_metadata`
* [ ] ChatGPT **new** plugin → Railway `/mcp` with **OAuth**; tunnel plugin stays until that passes
* [ ] Optional: `tools/list_changed` + stateful HTTP for faster ChatGPT discovery

## Key files

| Path | Role |
|---|---|
| `mcp_server.py` | Entry point — `create_server(auth_provider)` |
| `bridge/auth/` | Inbound auth: none, static, oauth |
| `bridge/auth/oauth.py` | WorkOS JWT verifier + well-known metadata |
| `bridge/config/` | Deployment settings |
| `bridge/diagnostics/` | Version, schema hash |
| `bridge/logging/` | MCP discovery logging |
| `bridge/transport/` | HTTP hardening, transport security |
| `services/tasks/` | Google Tasks MCP tools + API adapters |
| `start_tasks_bridge.sh` | Local orchestration |
| `Dockerfile` / `railway.toml` | Railway production deploy |
| `docs/local-dev.md` | Local setup |
| `docs/railway.md` | Railway deploy + oauth switch |
| `docs/mcp-oauth-design.md` | OAuth design (WorkOS resource server) |
| `docs/chatgpt-tunnel.md` | OpenAI tunnel setup |
| `docs/chatgpt-discovery.md` | Debugging ChatGPT tool discovery |
| `.github/workflows/ci.yml` | CI: unit tests + dependency audit + security scan |
| `.github/dependabot.yml` | Automated dependency update PRs |
| `scripts/check.sh` | Local pre-push gate (mirrors CI) |
| `scripts/build-menubar-app.sh` | Build macOS menu bar Tasks Bridge.app |
| `docs/macos-menubar.md` | Menu bar app setup |

## Docs

- [README.md](README.md) — quick start and layout
- [SECURITY.md](SECURITY.md) — secrets policy
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute

## Recent result

Pinned patched deps so CI `pip-audit` can pass: `cryptography==48.0.1` → `50.0.1` (CVE-2026-69247 / 69248 / 69249) and `PyJWT==2.10.1` → `2.13.0` (CVE-2025-45768 last-affected 2.10.1, plus 2026 PyJWT advisories). No MCP tool or `SERVER_VERSION` change. Local pytest 45 passed; pip-audit of the new pins reported no known vulnerabilities. OAuth verifier code unchanged (`bridge/auth/oauth.py` still uses PyJWT + JWKS).

## Next action

Push the requirements pin bump (not committed this session) so `test-and-scan` on `main` goes green. Then on Railway set `MCP_AUTH_MODE=oauth`, `WORKOS_AUTHKIT_DOMAIN`, and `MCP_OAUTH_ALLOWED_EMAIL`. Create a new ChatGPT plugin with OAuth; keep the tunnel plugin until it works.
