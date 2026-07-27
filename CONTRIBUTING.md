# Contributing

Thanks for your interest in Tasks Bridge. This project started as personal infrastructure for connecting Google Tasks to AI tools; it is shared publicly as a reference implementation others can fork and adapt.

## Scope

This is a **single-user bridge** today. Each deployment connects to **one** Google account via OAuth. Multi-tenant or shared hosting is out of scope unless explicitly discussed in an issue first.

## Before you start

1. Read [README.md](README.md) and [docs/local-dev.md](docs/local-dev.md).
2. Create your **own** Google Cloud OAuth client — do not use someone else's `credentials.json` or refresh token. See [docs/google-oauth.md](docs/google-oauth.md).
3. Never commit `.env`, `credentials.json`, or `token.json`.

## How to contribute

- **Bug reports** — open an issue with steps to reproduce, OS, and relevant logs (redact tokens).
- **Small fixes** — PRs welcome for clear bugs, doc improvements, and test coverage.
- **Features** — open an issue first for anything that changes MCP tool schemas, auth model, or deployment architecture.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_config.py
python test_bridge_diagnostics.py
```

Local Google API tests require OAuth files:

```bash
cp credentials.json.example credentials.json   # fill from your GCP project
python test_task_services.py "General"
```

## Code style

- Match existing patterns in the file you edit.
- Keep changes focused — avoid drive-by refactors.
- Update docs when behavior or env vars change.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
