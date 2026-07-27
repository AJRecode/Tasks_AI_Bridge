# Security

## Secrets

Never commit or publish:

- `.env` — OpenAI tunnel API keys
- `credentials.json` — Google OAuth client secret
- `token.json` — Google access/refresh tokens
- Any live refresh token or API key in docs, issues, or chat logs

Use `.env.example` and `credentials.json.example` as templates only.

## Before pushing to GitHub

1. Run `git status` — confirm secret files are not listed.
2. Run `git check-ignore -v credentials.json token.json .env` — all should match `.gitignore`.
3. Rotate credentials if they were ever exposed (chat, screenshots, accidental commit).
4. Do not commit `.cursor/`, `.tasks-bridge/`, or `tunnel-client` (all gitignored).

## Production (Railway)

- Store `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` as Railway **variables**, not in the repo.
- The server runs headless — no browser OAuth on the container.
- Task titles and notes pass through MCP responses; treat logs as potentially sensitive.

## Local

- `token.json` stays on your machine only.
- MCP Inspector and discovery timeline files under `.tasks-bridge/` may contain client user-agents; gitignored.

## Forking this project

Each fork needs its **own** Google Cloud OAuth client. See [docs/google-oauth.md](docs/google-oauth.md). Never use another operator's refresh token or client secret.

## Reporting

Open a GitHub issue for security concerns in this public repo. For your own deployment, review Google OAuth consent screen and ChatGPT connector permissions regularly.
