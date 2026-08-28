# MCP endpoint OAuth — exploration (ChatGPT + Railway)

**Status:** Exploratory / not committed. No implementation yet.

This document captures **open questions** about letting ChatGPT connect to Tasks Bridge over **public HTTPS** (Railway) without static bearer tokens — which the ChatGPT connector UI does not support today.

**Do not treat this as a fixed build plan.** The right answer may be “keep using the tunnel” or “use an external identity provider” — not a custom authorization server in this repo.

## August 28, 2026 — clarified handoff for hosted ChatGPT spike

### Historical blocker now confirmed

The blocker was **not Google Tasks OAuth and not Railway hosting itself**. Railway could host the bridge and the production path could authenticate onward to Google Tasks. The unresolved layer was **inbound authentication from ChatGPT to the public Railway MCP endpoint**.

Keep these two authorization relationships separate:

1. **ChatGPT → Tasks Bridge** — MCP-facing inbound authentication. This is the missing hosted-path layer.
2. **Tasks Bridge → Google Tasks** — Google OAuth. This already exists and must remain separate from MCP authentication.

The OpenAI Secure MCP Tunnel avoided the first problem by providing the working ChatGPT control-plane path to the local unauthenticated MCP endpoint. Direct Railway → ChatGPT requires a ChatGPT-compatible MCP OAuth path instead.

### Preferred next experiment

Use an **external MCP-capable IdP**, with **WorkOS/AuthKit as the first spike candidate**, and keep Tasks Bridge as an OAuth resource server rather than turning this repository into an identity platform.

Google directly is not the preferred MCP-facing IdP path. Google remains the downstream authorization provider for Google Tasks. Using Google login as the basis for MCP authentication would likely require additional authorization-server/broker behavior that an MCP-oriented IdP already supplies.

### Important dependency distinction

The current bridge uses the official Python MCP SDK:

```text
mcp==1.28.1
```

and imports:

```python
from mcp.server.fastmcp import FastMCP
```

Do **not** assume examples for the separate standalone FastMCP 2.x package are drop-in compatible. In particular, convenient provider integrations documented for standalone FastMCP may not exist in the same form in the official `mcp` package used here.

**Do not migrate MCP frameworks merely to add authentication.** First test whether the existing official MCP SDK architecture can support the required WorkOS resource-server/token-verification flow with a small amount of glue.

The intended seam already exists: [bridge/auth/oauth.py](../bridge/auth/oauth.py) and `AuthProvider.fastmcp_kwargs()` feeding the FastMCP constructor in [mcp_server.py](../mcp_server.py).

### Cursor / implementation handoff: time-boxed spike

The next engineering step should be a deliberately small experiment, not a production OAuth implementation:

1. Keep the existing Tasks tools, Google authorization, Railway deployment, and MCP framework unchanged.
2. Configure a WorkOS/AuthKit development application suitable for MCP OAuth.
3. Implement only the minimum `MCP_AUTH_MODE=oauth` behavior needed for Tasks Bridge to act as the protected MCP resource and validate WorkOS-issued access tokens.
4. Expose the MCP protected-resource metadata required for authorization-server discovery.
5. Deploy the spike to Railway over HTTPS.
6. Configure ChatGPT against the Railway `/mcp` endpoint.
7. Attempt one real end-to-end authentication and tool invocation with the local bridge and OpenAI tunnel turned off.

**Pass criterion:** ChatGPT authenticates directly to the Railway MCP endpoint, discovers Tasks Bridge tools, and successfully invokes at least one harmless read tool (for example `get_bridge_diagnostics` or `get_task_lists`) while the Mac/local tunnel is not participating.

**Fail criterion:** If the handshake fails because of an OAuth/MCP compatibility requirement, capture the exact failing requirement, endpoint, metadata field, registration mechanism, or token validation behavior and stop the spike. Do not respond by building a custom authorization server or migrating frameworks without a new decision.

### Only after the spike passes

Then productionize the existing OAuth seam: configuration/env vars, token validation, protected-resource metadata, 401/`WWW-Authenticate` behavior, automated tests, Railway documentation, security review, and operational diagnostics. Re-evaluate the IdP choice only if the WorkOS spike exposes a concrete incompatibility.

## What works today (certain)

| Path | Status | Notes |
|---|---|---|
| **ChatGPT + local tunnel** | **Works now** | [chatgpt-tunnel.md](chatgpt-tunnel.md) → `localhost:8000/mcp` |
| **Railway + static bearer** | **Works now** | `MCP_AUTH_MODE=static` — curl, scanners, Inspector, custom clients; **not** ChatGPT UI |
| **Railway + OAuth** | **Uncertain / planned** | Requires MCP-standard OAuth; approach TBD |

Inbound auth modes in code: `none` | `static` | `oauth` ([bridge/auth/](../bridge/auth/)). Only `none` and `static` are implemented. `oauth` fails fast until a deliberate choice is made.

## Problem statement

| Auth method | ChatGPT connector UI | Cursor localhost | curl / scripts |
|---|---|---|---|
| Static `MCP_API_TOKEN` bearer | **No** | N/A (local skips auth) | Yes |
| MCP OAuth (PKCE) | **Yes** | N/A | Via OAuth dance |
| OpenAI tunnel | **Yes** (control plane) | Yes | N/A |

**ChatGPT today:** OpenAI tunnel → `localhost:8000/mcp`.

**Railway today:** `MCP_AUTH_MODE=static` bearer on `/mcp` ([bridge/auth/static_bearer.py](../bridge/auth/static_bearer.py)).

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

When `MCP_AUTH_MODE=oauth` is implemented, wire through [bridge/auth/oauth.py](../bridge/auth/oauth.py) — not by extending [bridge/transport/http_security.py](../bridge/transport/http_security.py).

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
| `static` | Railway / scripts | Bearer via [bridge/auth/static_bearer.py](../bridge/auth/static_bearer.py) |
| `oauth` | ChatGPT + Railway HTTPS (TBD) | Stub in [bridge/auth/oauth.py](../bridge/auth/oauth.py) — not implemented |

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

- [ ] Wire `bridge/auth/oauth.py` to chosen IdP (resource server only)
- [ ] Env vars, Railway checklist, tests for metadata + 401 shape
- [ ] Revisit whether built-in AS (Option B) is still needed — default **no**

## Conflicts / touchpoints with current code

| Component | Role |
|---|---|
| [bridge/auth/oauth.py](../bridge/auth/oauth.py) | Future OAuth mode — IdP-backed resource server preferred |
| [bridge/auth/static_bearer.py](../bridge/auth/static_bearer.py) | Today’s Railway inbound auth |
| [bridge/transport/http_security.py](../bridge/transport/http_security.py) | Rate/size limits only |
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
