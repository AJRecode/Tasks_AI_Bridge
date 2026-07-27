# Railway deployment

Deploy Tasks Bridge as a public HTTPS MCP endpoint for ChatGPT (no local tunnel required).

```
GitHub  →  push  →  Railway  →  https://<app>.up.railway.app/mcp  →  ChatGPT
                                              ↓
                                    Google Tasks API
```

Public or private GitHub repos both work — Railway connects via GitHub the same way.

## Prerequisites

- Railway account linked to your GitHub repo
- Google Cloud OAuth client (Desktop app is fine for obtaining a refresh token)
- Google Tasks API enabled

## 1. Obtain a long-lived refresh token (one-time, local)

Railway cannot open a browser. Run the desktop OAuth flow **once on your machine**:

```bash
source .venv/bin/activate
python test_task_services.py "General"
```

Extract the refresh token from `token.json`:

```bash
python -c "import json; print(json.load(open('token.json'))['refresh_token'])"
```

Also note `client_id` and `client_secret` from `credentials.json` or `token.json`.

**Treat these as secrets.** Store them in Railway variables, not in git.

## 2. Railway service variables

Set in the Railway dashboard (Settings → Variables):

| Variable | Required | Notes |
|---|---|---|
| `MCP_API_TOKEN` | **Yes** | Long random secret for `Authorization: Bearer …` on `/mcp` |
| `GOOGLE_CLIENT_ID` | Yes | From OAuth client |
| `GOOGLE_CLIENT_SECRET` | Yes | From OAuth client |
| `GOOGLE_REFRESH_TOKEN` | Yes | From local `token.json` |
| `TASKS_BRIDGE_DEPLOYMENT` | Optional | Auto-detected from `RAILWAY_*`; set to `production` to force |
| `MCP_PUBLIC_HOST` | Optional | Auto-set from `RAILWAY_PUBLIC_DOMAIN` on Railway |
| `MCP_RATE_LIMIT_REQUESTS` | Optional | Default `60` requests/window/IP on `/mcp` |
| `MCP_MAX_REQUEST_BYTES` | Optional | Default `1048576` (1 MiB) |
| `TASKS_BRIDGE_PRODUCTION_ENV` | Optional | Default `production`; used to detect trusted Railway env |

Railway sets `PORT` and `RAILWAY_PUBLIC_DOMAIN` automatically.

Do **not** set `CONTROL_PLANE_*` on Railway unless you also run `tunnel-client` as a separate process pointing at the public URL.

Generate a strong MCP token locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 3. Deploy

This repo includes a `Dockerfile` and `railway.toml`.

1. Create a new Railway project from your GitHub repo.
2. Railway builds the Docker image and runs `python mcp_server.py`.
3. Health check: `GET /health` → `{"status":"ok",...}` (no auth required).
4. MCP endpoint: `https://<your-domain>/mcp` (requires bearer token).

## 4. Connect ChatGPT

1. In ChatGPT connector settings, add your Railway MCP URL: `https://<app>.up.railway.app/mcp`.
2. Configure the same bearer token you set as `MCP_API_TOKEN` in the connector auth settings.
3. Use **Refresh** after deploying a new server version.
4. Call `get_bridge_diagnostics` to verify `schema_hash` and `tool_names` match the deployment.

See [chatgpt-discovery.md](chatgpt-discovery.md) for debugging discovery lag.

## Preview / PR environments

Railway PR environments **inherit variables from the base environment by default**. To keep Google OAuth secrets out of untrusted preview deploys:

1. Mark `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` as **sealed** in Railway (not copied to PR environments), **or**
2. Disable PR environments for this service, **or**
3. Name your trusted production environment `production` and let the server refuse to boot if Google secrets appear in other Railway environments (see `TASKS_BRIDGE_PRODUCTION_ENV`).

The server fails fast on preview boot when Google secrets are present unless `ALLOW_PREVIEW_SECRETS=1`.

## Local vs production

| Concern | Local | Railway |
|---|---|---|
| Bind address | `127.0.0.1:8000` | `0.0.0.0:$PORT` |
| Google auth | `credentials.json` + browser | `GOOGLE_*` env vars |
| ChatGPT path | `tunnel-client` → localhost | Public HTTPS URL |
| Start script | `start_tasks_bridge.sh` | Docker `CMD` |
| Inspector | Optional dev tool | Not used |

Both modes share the same Python modules (`mcp_server.py`, `task_services.py`, etc.). Deployment mode is selected via environment variables (`config.py`).

## Security checklist

- [ ] `.env`, `token.json`, `credentials.json` are gitignored and not in git history
- [ ] Rotate any secrets that were ever pasted into chat or committed by mistake
- [ ] Railway variables hold Google OAuth secrets (not in repo)
- [ ] `MCP_API_TOKEN` is set in Railway and configured in ChatGPT connector auth
- [ ] Google OAuth secrets are sealed or excluded from PR preview environments
- [ ] OAuth client belongs to **your** Google Cloud project — see [google-oauth.md](google-oauth.md)
