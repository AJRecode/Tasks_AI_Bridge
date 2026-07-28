#!/usr/bin/env bash
# Run the same checks as .github/workflows/ci.yml (local pre-push gate).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Missing .venv — create one first:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing CI tools (pytest, pip-audit, bandit)..."
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q pytest pip-audit bandit

echo "==> pytest"
pytest -q

echo "==> pip-audit"
pip-audit -r requirements.txt

echo "==> bandit"
bandit -r auth config.py bridge_diagnostics.py google_auth.py google_tasks.py http_security.py mcp_server.py task_services.py \
  -s B104,B603,B607,B404,B110,B106

echo ""
echo "All checks passed."
