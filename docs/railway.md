# Railway deployment

Deploy Tasks Bridge as a **bearer-protected** public HTTPS MCP endpoint when `MCP_AUTH_MODE=static` (production default). **`MCP_AUTH_MODE=static` requires `MCP_API_TOKEN`** — locally and on Railway.

## Client access paths

| Path | Status | Notes |
|---|---|---|
| **ChatGPT + OpenAI tunnel** | **Works now** | [chatgpt-tunnel.md](chatgpt-tunnel.md) → `localhost:8000/mcp`. **Current ChatGPT-compatible path.** |
| **Railway + static bearer** | **Works now** | `MCP_AUTH_MODE=static` + `MCP_API_TOKEN`. Inspector (Custom Header), curl, scanners, compatible custom clients. **Not ChatGPT.** |
| **Railway + OAuth** | **Implemented; ChatGPT handshake unverified** | `MCP_AUTH_MODE=oauth` + WorkOS/AuthKit. ChatGPT connector **OAuth**. See **[mcp-oauth-design.md](mcp-oauth-design.md)**. |

**ChatGPT cannot authenticate to Railway with static bearer.** The ChatGPT plugin UI offers OAuth / No auth / Mixed, not `MCP_API_TOKEN`. Direct ChatGPT → Railway uses **`MCP_AUTH_MODE=oauth`** after WorkOS is configured. Keep the OpenAI tunnel plugin until that ChatGPT handshake succeeds.

Exactly one inbound auth mode is active per process (`none`, `static`, or `oauth`). Static bearer and OAuth do not run together.

```
ChatGPT (works now)     →  OpenAI tunnel  ←  tunnel-client  ←  localhost:8000/mcp
                                                                    (local Mac)

GitHub  →  Railway  →  https://<app>.up.railway.app/mcp
                              ↓
     MCP_AUTH_MODE=static + MCP_API_TOKEN  →  Inspector / curl / scanners / custom clients
                              ↓                           (not ChatGPT — OAuth required for that)
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
| `MCP_AUTH_MODE` | Optional | `none` (local default) \| `static` (production default) \| `oauth` (WorkOS). See [mcp-oauth-design.md](mcp-oauth-design.md) |
| `MCP_API_TOKEN` | **Yes when `static`** | Required whenever `MCP_AUTH_MODE=static`. Unused in `oauth` mode |
| `WORKOS_AUTHKIT_DOMAIN` | **Yes when `oauth`** | AuthKit origin, e.g. `https://fine-ash-09-staging.authkit.app` |
| `MCP_OAUTH_ALLOWED_EMAIL` | **Yes when `oauth`** | Comma-separated emails allowed to call `/mcp` (use the Gmail that signs into AuthKit) |
| `MCP_OAUTH_EXTRA_AUDIENCES` | Optional | Extra JWT `aud` values if ChatGPT omits `resource` |
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

### ChatGPT — OpenAI tunnel today (client access table row 1)

**ChatGPT does not connect to Railway with static bearer.** The connector UI has no field for `MCP_API_TOKEN`; direct ChatGPT → Railway requires **OAuth** (exploratory — see [MCP OAuth exploration](mcp-oauth-design.md)).

For ChatGPT, use the **OpenAI Secure MCP Tunnel** to localhost (see [chatgpt-tunnel.md](chatgpt-tunnel.md)):

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

## 5. ChatGPT over Railway HTTPS (`oauth`)

After this code is deployed, switch the Railway service from `static` to `oauth`. Static bearer and OAuth cannot run in the same process.

1. Confirm WorkOS **Connect → Configuration**: MCP Auth on, CIMD/DCR on, resource indicator `https://tasksaibridge-production.up.railway.app/mcp`.
2. Railway variables:
   - `MCP_AUTH_MODE=oauth`
   - `WORKOS_AUTHKIT_DOMAIN=https://fine-ash-09-staging.authkit.app`
   - `MCP_OAUTH_ALLOWED_EMAIL=` the **Gmail** you use to sign into WorkOS/AuthKit (comma-separate later if you add another WorkOS user)
   - Keep `GOOGLE_*` so tools can reach Tasks
   - You may leave `MCP_API_TOKEN` set; oauth mode ignores it
3. Redeploy. Logs should show `Auth mode: oauth`.
4. `GET /health` still 200 with no token. `POST /mcp` without a token should 401 with `WWW-Authenticate` containing `resource_metadata=`.
5. ChatGPT also fetches `/.well-known/oauth-authorization-server/mcp` on the **MCP host** (not only AuthKit). A 404 there produces “Something went wrong with setting up the connection” / Reconnect with **No app actions**.
6. Plugin URL must be exactly `https://tasksaibridge-production.up.railway.app/mcp` (`tasksaibridge` with **ai**). `https://tasksbridge-production.up.railway.app` is a different Railway hostname and returns `Application not found`.
7. In ChatGPT, **Reconnect** or create **New Bridges** (leave the **AJ Task MCP** tunnel plugin): authentication **OAuth**. Complete AuthKit login as that Gmail.

Until that handshake succeeds, keep using the tunnel plugin.

### WorkOS Redirects vs resource indicator

Do **not** put the Railway `/mcp` URL on WorkOS **Redirects**. That URL is a **resource indicator** on **Connect → Configuration** only.

- **External Sign-in URI** — leave empty (Standalone Connect, not this setup).
- **Google social login** — copy the callback URL WorkOS displays (typically a WorkOS/AuthKit Google callback) into Google Cloud Console **Authorized redirect URIs**. You copy WorkOS’s URI out; you do not invent one.
- **Applications → Redirects** (web app after AuthKit login) — skip for MCP. ChatGPT registers its own redirect via CIMD. Add a URI later only if ChatGPT errors with a specific `redirect_uri`.

Then return to **Connect → Configuration**.

## Preview / PR environments

Railway PR environments **inherit variables from the base environment by default**. To keep Google OAuth secrets out of untrusted preview deploys:

1. Mark `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` as **sealed** in Railway (not copied to PR environments), **or**
2. Disable PR environments for this service, **or**
3. Name your trusted production environment `production` and let the server refuse to boot if Google secrets appear in other Railway environments (see `TASKS_BRIDGE_PRODUCTION_ENV`).

The server fails fast on preview boot when Google secrets are present unless `ALLOW_PREVIEW_SECRETS=1`.

## Local vs production

| Concern | Local (default) | Railway `static` | Railway `oauth` |
|---|---|---|---|
| Bind address | `127.0.0.1:8000` | `0.0.0.0:$PORT` | `0.0.0.0:$PORT` |
| Google auth | `credentials.json` + browser | `GOOGLE_*` env vars | `GOOGLE_*` env vars |
| Inbound MCP auth | `none` — no bearer | `MCP_API_TOKEN` | WorkOS JWT + email allowlist |
| ChatGPT | **OpenAI tunnel** → localhost | No — connector has no bearer field | New plugin, authentication **OAuth** |
| Other HTTP clients | Inspector, Cursor | curl / Inspector with bearer | ChatGPT after AuthKit login |
| Rate limits | Per-process if enabled | Per-process, proxy-sensitive | Per-process, proxy-sensitive |

Both modes share the same Python modules (`mcp_server.py`, `bridge/`, `services/`). Deployment mode is selected via environment variables (`bridge/config`).

## Security checklist

- [ ] `.env`, `token.json`, `credentials.json` are gitignored and not in git history
- [ ] Rotate any secrets that were ever pasted into chat or committed by mistake
- [ ] Railway variables hold Google OAuth secrets (not in repo)
- [ ] `MCP_API_TOKEN` is set whenever `MCP_AUTH_MODE=static`
- [ ] For ChatGPT → Railway: `MCP_AUTH_MODE=oauth`, `WORKOS_AUTHKIT_DOMAIN`, and `MCP_OAUTH_ALLOWED_EMAIL` are set
- [ ] ChatGPT uses the **tunnel** plugin until the Railway OAuth handshake succeeds
- [ ] Google OAuth secrets are sealed or excluded from PR preview environments
- [ ] OAuth client belongs to **your** Google Cloud project — see [google-oauth.md](google-oauth.md)
