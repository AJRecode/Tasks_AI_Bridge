# Project Status

* **Last updated:** July 27, 2026
* **Server version:** `1.4.0` (`bridge_diagnostics.py`)
* **License:** MIT
* **Deployment modes:** `local` (default) | `production` (Railway via env)

## Summary

Tasks Bridge exposes **Google Tasks** to AI tools (ChatGPT, Cursor) through an MCP server. One Python codebase runs locally (native `.venv`) or on Railway (Docker). Local ChatGPT access uses the OpenAI Secure MCP Tunnel; production uses a public HTTPS MCP URL.

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
GitHub  →  Railway  →  https://<app>.up.railway.app/mcp  →  ChatGPT
                              ↓
                    google_auth (env vars)  →  Google Tasks API
```

| Mode | Entry | Google auth | ChatGPT path |
|---|---|---|---|
| Local | `python mcp_server.py` / `start_tasks_bridge.sh` | `credentials.json` + `token.json` | `tunnel-client` → localhost |
| Production | Docker / Railway | `GOOGLE_*` env vars | Public HTTPS MCP URL |

## MCP tools (10)

`get_bridge_diagnostics`, `get_task_lists`, `get_tasks`, `get_open_tasks`, `search_tasks`, `create_task_list`, `create_task`, `update_task`, `complete_task`, `move_task`.

## Verified working

| Capability | How to verify |
|---|---|
| Config local/production | `python test_config.py` |
| Diagnostics | `python test_bridge_diagnostics.py` |
| Google Tasks API (local) | `python test_task_services.py "General"` (requires OAuth files) |
| MCP HTTP + `/health` | `curl http://127.0.0.1:8000/health` |
| Local orchestration | `./start_tasks_bridge.sh --status` |
| Railway artifacts | `Dockerfile`, `railway.toml`, `/health` route |

## Runtime status

Run `./start_tasks_bridge.sh --status` for a live snapshot. PIDs and process details are not recorded here (they go stale in git).

## Known issues

* **Tunnel status false positive** — `--status` may show the tunnel as STALE because it looks for a persistent TCP connection to port 8000. `tunnel-client` probes on startup and connects on demand; check the tunnel Terminal window or `http://127.0.0.1:8080/ui`.
* **ChatGPT tool discovery lag** — new MCP tools may appear in Inspector before ChatGPT exposes them. Likely OpenAI registry propagation, not a stale server. See [docs/chatgpt-discovery.md](docs/chatgpt-discovery.md).
* **`oauth_metadata` warnings** — expected for this read-only server (no OAuth on the MCP endpoint).
* **`tools/list_changed` not enabled** — optional future enhancement.

## Roadmap

* [ ] First public GitHub release + Railway deploy
* [ ] Verify ChatGPT against production HTTPS URL
* [ ] Optional: OAuth web callback for multi-user deployments
* [ ] Optional: `tools/list_changed` + stateful HTTP for faster ChatGPT discovery

## Key files

| File | Role |
|---|---|
| `mcp_server.py` | FastMCP server, `/health`, MCP tools |
| `config.py` | Local vs production settings |
| `google_auth.py` | File OAuth (local) or env vars (Railway) |
| `start_tasks_bridge.sh` | Local orchestration only |
| `Dockerfile` / `railway.toml` | Railway production deploy |
| `docs/local-dev.md` | Local setup |
| `docs/railway.md` | Railway deploy |
| `docs/chatgpt-tunnel.md` | OpenAI tunnel setup |
| `docs/chatgpt-discovery.md` | Debugging ChatGPT tool discovery |

## Docs

- [README.md](README.md) — quick start and layout
- [SECURITY.md](SECURITY.md) — secrets policy
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
