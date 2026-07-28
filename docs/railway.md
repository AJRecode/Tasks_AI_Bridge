# Railway deployment

Deploy Tasks Bridge as a **bearer-protected** public HTTPS MCP endpoint when `MCP_AUTH_MODE=static` (production default).

## Client access paths

| Path | Status | Notes |
|---|---|---|
| **ChatGPT + local tunnel** | **Works now** | [chatgpt-tunnel.md](chatgpt-tunnel.md) → `localhost:8000/mcp`. ChatGPT does not use Railway HTTPS today. |
| **Railway + static bearer** | **Works now** | `MCP_AUTH_MODE=static` + `MCP_API_TOKEN`. curl, scanners, MCP Inspector (bearer header), compatible custom clients. **Not** the ChatGPT connector UI. |
| **Railway + OAuth** | **Uncertain / exploratory** | `MCP_AUTH_MODE=oauth` stub — external IdP preferred over custom auth server. See **[mcp-oauth-design.md](mcp-oauth-design.md)**. |

Exactly one inbound auth mode is active per process (`none`, `static`, or `oauth`). Static bearer and OAuth do not run together.

```
GitHub  →  push  →  Railway  →  https://<app>.up.railway.app/mcp  →  curl / Inspector / custom clients
                                              ↓
                                    Google Tasks API

ChatGPT (today)  →  OpenAI tunnel  ←  tunnel-client  ←  localhost:8000/mcp
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
| `MCP_AUTH_MODE` | Optional | `none` (local default) \| `static` (production default) \| `oauth` (planned). See [mcp-oauth-design.md](mcp-oauth-design.md) |
| `MCP_API_TOKEN` | **Yes** (when `static`) | Long random secret for `Authorization: Bearer …` on `/mcp` |
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

## 4. Connect clients

### ChatGPT — tunnel today; Railway HTTPS planned

**Status:** direct Railway → ChatGPT is **exploratory** — see [MCP OAuth exploration](mcp-oauth-design.md). Prefer external IdP over building an authorization server. Do not expect ChatGPT to connect to the public Railway URL until a path is proven.

The ChatGPT connector UI supports **OAuth**, not static bearer tokens. **`MCP_API_TOKEN` cannot be entered in ChatGPT today.**

For ChatGPT, keep using the **OpenAI Secure MCP Tunnel** to localhost (see [chatgpt-tunnel.md](chatgpt-tunnel.md)):

```
ChatGPT  →  OpenAI tunnel  ←  tunnel-client  ←  http://127.0.0.1:8000/mcp
```

Your Mac runs MCP + tunnel; ChatGPT never hits the public Railway URL directly. Railway deploy is optional for ChatGPT until OAuth is proven practical — exploration doc: **[mcp-oauth-design.md](mcp-oauth-design.md)**.

### Bearer clients — Railway HTTPS works today

Bearer-protected Railway `/mcp` works now with:

- **curl** — smoke tests and JSON-RPC probes
- **Security scanners** — verify 401 without token, rate limits, etc.
- **MCP Inspector** — point at the public URL and set the bearer header (dev/debug)
- **Compatible custom MCP clients** — any client that can send `Authorization: Bearer …`

For those clients, use:

```text
https://<app>.up.railway.app/mcp
```

with the same value as Railway `MCP_API_TOKEN`.

Verify with:

```bash
curl -i https://YOUR-APP.up.railway.app/mcp
# expect 401 without token

curl -i -X POST https://YOUR-APP.up.railway.app/mcp \
  -H "Authorization: Bearer YOUR_MCP_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

See [chatgpt-discovery.md](chatgpt-discovery.md) for debugging ChatGPT tool discovery when using the tunnel.

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
| ChatGPT path | `tunnel-client` → localhost (OpenAI tunnel auth) | **Exploratory** — direct HTTPS only if external IdP + ChatGPT spike succeeds |
| Bearer clients | Optional locally | curl, scanners, Inspector, custom clients on public HTTPS |
| Start script | `start_tasks_bridge.sh` | Docker `CMD` |
| Inspector | Optional dev tool | Not used |

Both modes share the same Python modules (`mcp_server.py`, `task_services.py`, etc.). Deployment mode is selected via environment variables (`config.py`).

## Security checklist

- [ ] `.env`, `token.json`, `credentials.json` are gitignored and not in git history
- [ ] Rotate any secrets that were ever pasted into chat or committed by mistake
- [ ] Railway variables hold Google OAuth secrets (not in repo)
- [ ] `MCP_API_TOKEN` is set in Railway (blocks anonymous `/mcp` access)
- [ ] ChatGPT uses the **tunnel** path unless/until an external-IdP OAuth spike succeeds
- [ ] Google OAuth secrets are sealed or excluded from PR preview environments
- [ ] OAuth client belongs to **your** Google Cloud project — see [google-oauth.md](google-oauth.md)
