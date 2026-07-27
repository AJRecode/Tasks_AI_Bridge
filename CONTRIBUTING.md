# Contributing

Thanks for your interest in Tasks Bridge. This project started as personal infrastructure for connecting Google Tasks to AI tools; it is shared publicly as a reference implementation others can fork and adapt.

## Scope

This is a **single-user bridge** today. Each deployment connects to **one** Google account via OAuth. Multi-tenant or shared hosting is out of scope unless explicitly discussed in an issue first.

## Before you start

1. Read [README.md](README.md) and [docs/local-dev.md](docs/local-dev.md).
2. Create your **own** Google Cloud OAuth client — do not use someone else's `credentials.json` or refresh token. See [docs/google-oauth.md](docs/google-oauth.md).
3. Never commit `.env`, `credentials.json`, or `token.json`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Tests and CI checks (run before you push)

GitHub Actions runs the same checks on every push/PR to `main`. Run them locally first:

```bash
./scripts/check.sh
```

That script runs, in order:

1. **pytest** — unit tests (no Google account required)
2. **pip-audit** — known CVE scan on `requirements.txt`
3. **bandit** — security lint on application source files

Install CI tools once if you prefer to run steps manually:

```bash
pip install pytest pip-audit bandit
pytest -q
pip-audit -r requirements.txt
bandit -r config.py bridge_diagnostics.py google_auth.py google_tasks.py mcp_server.py task_services.py \
  -s B104,B603,B607,B404,B110,B106
```

### What pytest covers

| File | Type | In CI? | Needs OAuth? |
|---|---|---|---|
| `test_config.py` | Unit | Yes | No |
| `test_bridge_diagnostics.py` | Unit | Yes | No |
| `test_http_security.py` | Unit (401/auth) | Yes | No |
| `test_task_services.py` | Integration smoke | No | Yes |
| `test_write_task_services.py` | Integration smoke | No | Yes |
| `test_create_task_list.py` | Integration smoke | No | Yes |

Pytest auto-discovers `test_*` functions in `test_*.py` files. Only the first two files use that pattern today, so CI runs **7 unit tests** with no network or secrets.

Run a single file:

```bash
pytest test_config.py -v
pytest test_bridge_diagnostics.py -v
```

Legacy style (still works):

```bash
python test_config.py
python test_bridge_diagnostics.py
```

### Google API integration tests (manual, optional)

These hit your live Google Tasks account. Run after OAuth setup when you change task/API code:

```bash
cp credentials.json.example credentials.json   # fill from your GCP project
python test_task_services.py "General"
python test_write_task_services.py "General"
python test_create_task_list.py
```

## Before pushing to GitHub

See [SECURITY.md](SECURITY.md). Minimum checklist:

1. `./scripts/check.sh` — all green locally
2. `git status` — no secret files listed
3. `git check-ignore -v credentials.json token.json .env` — all ignored
4. Push; confirm the **Actions** tab shows CI passing

After the repo is on GitHub, Dependabot activates from [`.github/dependabot.yml`](.github/dependabot.yml) (weekly update PRs for pip, Docker, and GitHub Actions). No extra config file needed beyond pushing that file.

Optional on GitHub (**Settings → Code security and analysis**): confirm **Dependabot alerts** and **Dependabot security updates** are enabled.

## How to contribute

- **Bug reports** — open an issue with steps to reproduce, OS, and relevant logs (redact tokens).
- **Small fixes** — PRs welcome for clear bugs, doc improvements, and test coverage.
- **Features** — open an issue first for anything that changes MCP tool schemas, auth model, or deployment architecture.

## Code style

- Match existing patterns in the file you edit.
- Keep changes focused — avoid drive-by refactors.
- Update docs when behavior or env vars change.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
