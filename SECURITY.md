# Security

## Secrets

Never commit or publish:

- `.env` — OpenAI tunnel API keys, `MCP_API_TOKEN`, and other secrets
- `credentials.json` — Google OAuth client secret
- `token.json` — Google access/refresh tokens
- Any live refresh token or API key in docs, issues, or chat logs

Use `.env.example` and `credentials.json.example` as templates only.

## Before pushing to GitHub

1. Run `./scripts/check.sh` — same pytest, pip-audit, and bandit checks as GitHub CI.
2. Run `git status` — confirm secret files are not listed.
3. Run `git check-ignore -v credentials.json token.json .env` — all should match `.gitignore`.
4. Rotate credentials if they were ever exposed (chat, screenshots, accidental commit).
5. Do not commit `.cursor/`, `.tasks-bridge/`, or `tunnel-client` (all gitignored).

## Production (Railway)

- Store `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` as Railway **variables**, not in the repo.
- Store `MCP_API_TOKEN` as a Railway variable; clients must send `Authorization: Bearer <token>` on `/mcp`.
- Prefer **sealed** Railway variables for Google OAuth secrets so PR preview environments do not inherit them.
- The server runs headless — no browser OAuth on the container.
- Task titles and notes pass through MCP responses; treat logs as potentially sensitive.

## Rate limiting (Railway / production)

`/mcp` rate limits in `bridge/transport/http_security.py` are intentionally **simple**:

- **Keyed by** ASGI client IP (per process, in memory)
- **Not** durable across restarts or Railway replicas
- **Proxy-sensitive** — Railway’s edge may collapse many callers into one shared IP

For this **single-user** bridge, that is acceptable. Treat rate limits as a **basic abuse guard** (runaway clients, accidental loops), **not** as strong authorization or per-user quotas. **Access control** on public HTTPS is `MCP_AUTH_MODE=static` + `MCP_API_TOKEN`.

## Local

- `token.json` stays on your machine only.
- MCP Inspector and discovery timeline files under `.tasks-bridge/` may contain client user-agents; gitignored.

## Forking this project

Each fork needs its **own** Google Cloud OAuth client. See [docs/google-oauth.md](docs/google-oauth.md). Never use another operator's refresh token or client secret.

## Reporting

Open a GitHub issue for security concerns in this public repo. For your own deployment, review Google OAuth consent screen and ChatGPT connector permissions regularly.
