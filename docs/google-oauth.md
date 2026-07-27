# Google OAuth setup

Each Tasks Bridge deployment needs its **own** Google Cloud OAuth credentials. You cannot share `credentials.json` or `token.json` between users or publish them in git.

## 1. Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or select an existing one).
3. Enable the **Google Tasks API** for that project.

## 2. OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**.
2. Choose **External** (unless you use a Google Workspace org internal app).
3. Fill in app name, support email, and developer contact.
4. Add scope: `https://www.googleapis.com/auth/tasks`.
5. Add your Google account as a **test user** while the app is in **Testing** mode.

### Testing mode limits

Apps in **Testing** publishing status are limited to users listed as test users (typically ~100). That is fine for personal use. To allow arbitrary Google accounts, you must complete Google's verification process — not required for a single-user bridge.

## 3. OAuth client (Desktop)

1. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Download the JSON and save it as `credentials.json` in the project root (gitignored).

Or copy fields from the console into `credentials.json.example` format.

## 4. Authorize locally (one-time browser flow)

```bash
source .venv/bin/activate
python test_task_services.py "General"
```

This opens a browser, completes consent, and writes `token.json` (gitignored).

## 5. Production (Railway)

Railway cannot open a browser. Extract values from your local files:

```bash
python -c "import json; print(json.load(open('token.json'))['refresh_token'])"
```

Set in Railway variables (never in git):

| Variable | Source |
|---|---|
| `GOOGLE_CLIENT_ID` | `credentials.json` or `token.json` |
| `GOOGLE_CLIENT_SECRET` | `credentials.json` or `token.json` |
| `GOOGLE_REFRESH_TOKEN` | `token.json` |

See [railway.md](railway.md) for deploy steps.

## Security reminders

- Rotate credentials if they were ever pasted into chat, issues, or committed by mistake.
- Treat task titles and notes as personal data in logs and MCP responses.
- Review OAuth consent and ChatGPT connector permissions periodically.
