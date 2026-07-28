# Railway deployment

Deploy Tasks Bridge as a **bearer-protected** public HTTPS MCP endpoint when `MCP_AUTH_MODE=static` (production default). **`MCP_AUTH_MODE=static` requires `MCP_API_TOKEN`** — locally and on Railway.

## Client access paths

| Path | Status | Notes |
|---|---|---|
| **ChatGPT + local tunnel** | **Works now** | [chatgpt-tunnel.md](chatgpt-tunnel.md) → `localhost:8000/mcp`. ChatGPT does not use Railway HTTPS today. |
| **Railway + static bearer** | **Works now** | `MCP_AUTH_MODE=static` + `MCP_API_TOKEN`. curl, scanners, MCP Inspector (bearer header), compatible custom clients. **Not** the ChatGPT connector UI. |
| **Railway + OAuth** | **Uncertain / exploratory** | `MCP_AUTH_MODE=oauth` stub — external IdP preferred over custom auth server. See **[mcp-oauth-design.md](mcp-oauth-design.md)**. |

Exactly one inbound auth mode is active per process (`none`, `static`, or `oauth`). Static bearer and OAuth do not run together.

```
ChatGPT (works now)     →  OpenAI tunnel  ←  tunnel-client  ←  localhost:8000/mcp
                                                                    (local Mac)

GitHub  →  Railway  →  https://<app>.up.railway.app/mcp
                              ↓
              MCP_AUTH_MODE=static + MCP_API_TOKEN  →  curl / Inspector / custom clients
                              ↓
              GOOGLE_* env vars  →  Google Tasks API
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
| `MCP_AUTH_MODE` | Optional | `none` (local default) \| `static` (production default) \| `oauth` (exploratory). See [mcp-oauth-design.md](mcp-oauth-design.md) |
| `MCP_API_TOKEN` | **Yes when `static`** | Required whenever `MCP_AUTH_MODE=static` (local or Railway). `Authorization: Bearer …` on `/mcp` |
| `GOOGLE_CLIENT_ID` | Yes | From OAuth client |
| `GOOGLE_CLIENT_SECRET` | Yes | From OAuth client |
| `GOOGLE_REFRESH_TOKEN` | Yes | From local `token.json` |
| `TASKS_BRIDGE_DEPLOYMENT` | Optional | Auto-detected from `RAILWAY_*`; set to `production` to force |
| `MCP_PUBLIC_HOST` | Optional | Auto-set from `RAILWAY_PUBLIC_DOMAIN` on Railway |
| `MCP_RATE_LIMIT_REQUESTS` | Optional | Default `60` requests/window/IP on `/mcp` — **per process**, proxy-sensitive (see below) |
| `MCP_MAX_REQUEST_BYTES` | Optional | Default `1048576` (1 MiB) |
| `TASKS_BRIDGE_PRODUCTION_ENV` | Optional | Default `production`; used to detect trusted Railway env |

Railway sets `PORT` and `RAILWAY_PUBLIC_DOMAIN` automatically.

Do **not** set `CONTROL_PLANE_*` on Railway unless you also run `tunnel-client` as a separate process pointing at the public URL.

Generate a strong MCP token locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Rate limits (per-process, proxy-sensitive)

`/mcp` rate limits are enforced **in memory per server process**, keyed by the client IP on the ASGI connection. On Railway, traffic often arrives through a **shared proxy IP**, so many distinct clients can count against the same bucket; replicas do not share counters. For this single-user service, treat limits as a **basic abuse guard** — tune `MCP_RATE_LIMIT_REQUESTS` / `MCP_RATE_LIMIT_WINDOW_SECONDS` if needed, but rely on **`MCP_API_TOKEN`** for real access control.

## 3. Deploy

This repo includes a `Dockerfile` and `railway.toml`.

1. Create a new Railway project from your GitHub repo.
2. Railway builds the Docker image and runs `python mcp_server.py`.
3. Health check: `GET /health` → `{"status":"ok",...}` (no auth required).
4. MCP endpoint: `https://<your-domain>/mcp` (requires bearer token when `static`).

## 4. Connect clients

### ChatGPT — tunnel today (client access table row 1)

**Status:** direct Railway → ChatGPT is **exploratory** — see [MCP OAuth exploration](mcp-oauth-design.md). Do not expect ChatGPT to connect to the public Railway URL until a path is proven.

The ChatGPT connector UI supports **OAuth**, not static bearer tokens. **`MCP_API_TOKEN` cannot be entered in ChatGPT today.**

For ChatGPT, keep using the **OpenAI Secure MCP Tunnel** to localhost (see [chatgpt-tunnel.md](chatgpt-tunnel.md)):

```
ChatGPT  →  OpenAI tunnel  ←  tunnel-client  ←  http://127.0.0.1:8000/mcp
```

Your Mac runs MCP + tunnel; ChatGPT never hits the public Railway URL directly.

### Bearer clients — Railway HTTPS (client access table row 2)

Bearer-protected Railway `/mcp` works now with:

- **curl** — smoke tests and JSON-RPC probes
- **Security scanners** — verify 401 + `WWW-Authenticate` without token, rate limits, etc.
- **MCP Inspector** — point at the public URL and add a **Custom Header** (not OAuth 2.0):
  - **Header name:** `Authorization`
  - **Header value:** `Bearer <MCP_API_TOKEN>`
- **Compatible custom MCP clients** — any client that can send `Authorization: Bearer …` (scheme is case-insensitive)

For those clients, use:

```text
https://<app>.up.railway.app/mcp
```

with the same value as Railway `MCP_API_TOKEN`.

Verify with:

```bash
curl -i https://YOUR-APP.up.railway.app/mcp
# expect 401 without token and: WWW-Authenticate: Bearer realm="Tasks Bridge MCP"

curl -i -X POST https://YOUR-APP.up.railway.app/mcp \
  -H "Authorization: Bearer YOUR_MCP_API_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
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

| Concern | Local (default) | Railway (`static`) |
|---|---|---|
| Bind address | `127.0.0.1:8000` | `0.0.0.0:$PORT` |
| Google auth | `credentials.json` + browser | `GOOGLE_*` env vars |
| Inbound MCP auth | `none` — no bearer | `static` + `MCP_API_TOKEN` required |
| ChatGPT | **Tunnel** → localhost | **Not Railway HTTPS** — use tunnel on your Mac |
| Bearer clients | Only if you set `MCP_AUTH_MODE=static` + token | curl, scanners, Inspector, custom clients |
| Rate limits | Per-process if enabled | Per-process, proxy-sensitive |

Both modes share the same Python modules (`mcp_server.py`, `bridge/`, `services/`). Deployment mode is selected via environment variables (`bridge/config`).

## Security checklist

- [ ] `.env`, `token.json`, `credentials.json` are gitignored and not in git history
- [ ] Rotate any secrets that were ever pasted into chat or committed by mistake
- [ ] Railway variables hold Google OAuth secrets (not in repo)
- [ ] `MCP_API_TOKEN` is set whenever `MCP_AUTH_MODE=static`
- [ ] ChatGPT uses the **tunnel** path (client access table row 1)
- [ ] Google OAuth secrets are sealed or excluded from PR preview environments
- [ ] OAuth client belongs to **your** Google Cloud project — see [google-oauth.md](google-oauth.md)
