# MCP endpoint OAuth — exploration (ChatGPT + Railway)

**Status:** Exploratory / not committed. No implementation yet.

This document captures **open questions** about letting ChatGPT connect to Tasks Bridge over **public HTTPS** (Railway) without static bearer tokens — which the ChatGPT connector UI does not support today.

**Do not treat this as a fixed build plan.** The right answer may be “keep using the tunnel” or “use an external identity provider” — not a custom authorization server in this repo.

## What works today (certain)

| Path | Status | Notes |
|---|---|---|
| **ChatGPT + local tunnel** | **Works now** | [chatgpt-tunnel.md](chatgpt-tunnel.md) → `localhost:8000/mcp` |
| **Railway + static bearer** | **Works now** | `MCP_AUTH_MODE=static` — curl, scanners, Inspector, custom clients; **not** ChatGPT UI |
| **Railway + OAuth** | **Uncertain / planned** | Requires MCP-standard OAuth; approach TBD |

Inbound auth modes in code: `none` | `static` | `oauth` ([auth/](../auth/)). Only `none` and `static` are implemented. `oauth` fails fast until a deliberate choice is made.

## Problem statement

| Auth method | ChatGPT connector UI | Cursor localhost | curl / scripts |
|---|---|---|---|
| Static `MCP_API_TOKEN` bearer | **No** | N/A (local skips auth) | Yes |
| MCP OAuth (PKCE) | **Yes** | N/A | Via OAuth dance |
| OpenAI tunnel | **Yes** (control plane) | Yes | N/A |

**ChatGPT today:** OpenAI tunnel → `localhost:8000/mcp`.

**Railway today:** `MCP_AUTH_MODE=static` bearer on `/mcp` ([auth/static_bearer.py](../auth/static_bearer.py)).

**Possible future goal:** ChatGPT uses `https://<app>.up.railway.app/mcp` directly — **only if** we find a practical OAuth path that does not turn this single-user bridge into an auth product.

## Design principle: do not over-engineer OAuth

Tasks Bridge is a **personal bridge**, not an identity platform.

**First question (before any code):** Can we integrate with an **existing, standards-compliant identity provider** (IdP) and run Tasks Bridge as an **OAuth resource server only**?

That means:

- IdP hosts login, MFA, token issuance, and (ideally) authorization-server metadata
- Tasks Bridge validates access tokens and exposes MCP protected-resource metadata
- We do **not** own `/authorize`, `/token`, client registration, or token storage unless forced by a spike

Building a bespoke authorization server (even a “minimal” one) is **discouraged** unless external IdP integration fails ChatGPT + MCP requirements in practice.

## MCP + ChatGPT requirements (spec summary)

If we pursue Railway HTTPS for ChatGPT, clients expect roughly:

1. **Protected Resource Metadata (RFC 9728)** on the MCP host  
   - e.g. `GET https://<host>/.well-known/oauth-protected-resource/mcp`

2. **Authorization Server Metadata (RFC 8414)** — usually on the **IdP**, not necessarily on Tasks Bridge  
   - e.g. `GET https://<idp>/.well-known/oauth-authorization-server`

3. **OAuth 2.1 authorization code + PKCE (S256)**  
   - ChatGPT may use dynamic client registration (DCR) or a pre-registered client — **compatibility must be verified**

4. **401 + WWW-Authenticate (optional)** pointing at resource metadata

See [MCP authorization spec](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) and [OpenAI Apps SDK auth guide](https://developers.openai.com/apps-sdk/build/auth).

**Unknown until spiked:** whether ChatGPT accepts a **third-party issuer**, which IdPs work without custom DCR, and whether Railway routing preserves well-known paths.

## FastMCP capabilities (resource server angle)

Our dependency `mcp>=1.28.1` / FastMCP supports resource-server patterns:

- `auth=AuthSettings(issuer_url=..., resource_server_url=...)`
- `token_verifier` → validate bearer tokens on `/mcp`
- Protected resource routes via `create_protected_resource_routes`

It also supports mounting a **local authorization server** (`auth_server_provider=…`). That path exists in the SDK but is **not the preferred direction** for this project unless external IdP integration is ruled out.

When `MCP_AUTH_MODE=oauth` is implemented, wire through [auth/oauth.py](../auth/oauth.py) — not by extending [http_security.py](../http_security.py).

Google Tasks OAuth (`GOOGLE_*`) stays **separate** — it authorizes the server to Google. MCP OAuth would authorize **clients to your MCP server**.

## Options (preference order — all uncertain)

### Option A — External IdP (evaluate first)

Examples: Auth0, Okta, Cognito, Clerk, or any OIDC/OAuth 2.1 provider that meets MCP + ChatGPT constraints.

- Tasks Bridge: resource server + `token_verifier` only
- IdP: login, tokens, authorization-server metadata
- **Pros:** No custom auth server; battle-tested security; fits “don’t own identity”
- **Cons:** Extra service/cost; must confirm ChatGPT + DCR + issuer URL compatibility
- **Open work:** Pick one IdP, run a **short spike** with ChatGPT against Railway or ngrok

### Option B — Built-in authorization server (fallback only)

Co-locate `/authorize`, `/token`, `/register` on the Railway host via FastMCP `auth_server_provider`.

- **Pros:** No third-party dependency
- **Cons:** We own token storage, rotation, consent UI, DCR hardening, and incident response — **poor fit for a personal bridge**
- **Status:** **Not recommended** unless Option A fails a verified ChatGPT handshake

### Option C — Tunnel only (current default)

No Railway OAuth work; Mac runs MCP + tunnel for ChatGPT.

- **Pros:** Already works; zero auth-server scope
- **Cons:** No always-on ChatGPT without local machine

**Working assumption:** **Option C** remains the default for ChatGPT. **Option A** is the only OAuth path worth serious investigation. **Option B** is a last resort.

## Target architecture if external IdP works (illustrative)

```
https://tasks-bridge.up.railway.app
├── /mcp                                    ← MCP (OAuth access token)
└── /.well-known/oauth-protected-resource/mcp

https://<your-idp>/
├── /.well-known/oauth-authorization-server
├── /authorize
└── /token
```

Exact URLs and env vars depend on the IdP chosen — **not specified here**.

## Auth mode switch (code today)

| `MCP_AUTH_MODE` | Use case | Behavior |
|---|---|---|
| `none` | Local dev (default) | No inbound auth on `/mcp` |
| `static` | Railway / scripts | Bearer via [auth/static_bearer.py](../auth/static_bearer.py) |
| `oauth` | ChatGPT + Railway HTTPS (TBD) | Stub in [auth/oauth.py](../auth/oauth.py) — not implemented |

Static bearer and OAuth must **not** both wrap `/mcp`.

## Suggested next steps (investigation, not implementation schedule)

### Phase 0 — Decide whether to pursue OAuth at all

- [ ] Confirm ChatGPT + tunnel remains acceptable for daily use
- [ ] If yes for always-on Railway ChatGPT, proceed to Phase 1; otherwise stop here

### Phase 1 — External IdP spike (small, time-boxed)

- [ ] Select one standards-compliant IdP with OAuth 2.1 + PKCE
- [ ] Confirm IdP metadata URLs, audience/resource indicators, and ChatGPT connector behavior
- [ ] Spike FastMCP `token_verifier` + protected-resource metadata on HTTPS (ngrok or Railway)
- [ ] One end-to-end ChatGPT handshake — document pass/fail; **no production code until pass**

### Phase 2 — Implement only if Phase 1 passes

- [ ] Wire `auth/oauth.py` to chosen IdP (resource server only)
- [ ] Env vars, Railway checklist, tests for metadata + 401 shape
- [ ] Revisit whether built-in AS (Option B) is still needed — default **no**

## Conflicts / touchpoints with current code

| Component | Role |
|---|---|
| [auth/oauth.py](../auth/oauth.py) | Future OAuth mode — IdP-backed resource server preferred |
| [auth/static_bearer.py](../auth/static_bearer.py) | Today’s Railway inbound auth |
| [http_security.py](../http_security.py) | Rate/size limits only |
| [mcp_server.py](../mcp_server.py) | `create_server(auth_provider=…)` |
| [docs/railway.md](railway.md) | Client access paths; link here |

## Security notes (single-user)

- MCP OAuth protects **who can call your MCP server**
- Google OAuth protects **which Google account’s Tasks** the server uses
- Do not expose Google refresh tokens to ChatGPT
- Prefer HTTPS on Railway (already true)
- Avoid operating a custom authorization server unless there is no viable IdP path

## References

- [MCP Authorization spec](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [OpenAI Apps SDK — Authenticate users](https://developers.openai.com/apps-sdk/build/auth)
- [RFC 9728 — Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- FastMCP: `mcp.server.auth.settings.AuthSettings`, `token_verifier`
