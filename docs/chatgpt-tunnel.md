# ChatGPT + Cursor: Tasks Bridge Setup

Tasks Bridge exposes your Google Tasks through MCP. **HTTP on port 8000 is the default.** ChatGPT reaches it through OpenAI's **Secure MCP Tunnel** (recommended). Cursor can use HTTP or stdio.

## Architecture

```
ChatGPT  →  OpenAI tunnel endpoint  ←  tunnel-client  ←  http://127.0.0.1:8000/mcp  ←  mcp_server.py
Cursor   →  http://127.0.0.1:8000/mcp   (or stdio subprocess)
                ↓
           task_services.py  →  Google Tasks API
```

---

## One-time setup

### 1. Python dependencies

```bash
cd Tasks_AI_Bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Google OAuth (`credentials.json`, `token.json`) must already work. Test with:

```bash
python test_task_services.py "Health"
```

### 2. OpenAI Platform tunnel

1. Open [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels) (or Tunnels in your org).
2. Create a tunnel and copy the **`tunnel_id`** (starts with `tunnel_`).
3. Create a **Runtime API key** with **Tunnels Read + Use** permissions.
4. Associate the tunnel with your **ChatGPT workspace** (required or it won't appear in ChatGPT).

### 3. Install `tunnel-client`

Download the binary for macOS from [openai/tunnel-client releases](https://github.com/openai/tunnel-client/releases) and put it on your `PATH`, or install per OpenAI docs.

### 4. Initialize the tunnel profile (once)

```bash
export CONTROL_PLANE_API_KEY="your-runtime-api-key"

tunnel-client init \
  --profile tasks-bridge \
  --tunnel-id "tunnel_your_id_here" \
  --mcp-server-url "http://127.0.0.1:8000/mcp"

tunnel-client doctor --profile tasks-bridge --explain
```

### 5. Local secrets file

```bash
cp .env.example .env
```

Edit `.env` (never commit it):

```bash
CONTROL_PLANE_API_KEY=your-runtime-api-key
CONTROL_PLANE_TUNNEL_ID=tunnel_your_id_here
TUNNEL_CLIENT_PROFILE=tasks-bridge
```

**Inbound auth:** keep **`MCP_AUTH_MODE=none`** (or omit it) for ChatGPT. The tunnel forwards requests to localhost but does **not** send `Authorization: Bearer`. If you set `MCP_AUTH_MODE=static`, ChatGPT will get **401** from your MCP server. Static bearer is for Railway and Inspector testing — see [local-dev.md](local-dev.md).

---

## Daily use

Start everything:

```bash
./start_tasks_bridge.sh
```

This starts:

1. **MCP HTTP server** on `http://127.0.0.1:8000/mcp` (if not already running)
2. **`tunnel-client`** (if `.env` is configured)

Stop the HTTP server: Ctrl+C in that terminal, or:

```bash
lsof -ti :8000 | xargs kill
```

### ChatGPT connector

1. Enable **Developer Mode** in ChatGPT (if your plan/workspace allows it).
2. Go to [ChatGPT Connectors](https://chatgpt.com/#settings/Connectors).
3. Create a custom connector → **Connection: Tunnel**.
4. Select your tunnel or paste the same `tunnel_id` from `.env`.
5. Keep `tunnel-client` running while using ChatGPT.

---

## Cursor setup

### Option A — HTTP (default, matches ChatGPT local server)

Use `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "tasks-bridge": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Run `./start_tasks_bridge.sh` or `python mcp_server.py` first. Restart Cursor after config changes.

### Option B — Stdio (Cursor spawns its own process)

No HTTP server needed for Cursor. Update `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "tasks-bridge": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["${workspaceFolder}/mcp_server.py", "--stdio"]
    }
  }
}
```

Or run manually:

```bash
python mcp_server.py --stdio
```

**Note:** Stdio and HTTP cannot share one process. Use HTTP if you want one server for both Cursor and ChatGPT (`tunnel-client` → localhost:8000).

---

## Manual commands

| Task | Command |
|---|---|
| HTTP server only | `python mcp_server.py` |
| Stdio server only | `python mcp_server.py --stdio` |
| Tunnel only | `tunnel-client run --profile tasks-bridge` |
| Check tunnel | `tunnel-client doctor --profile tasks-bridge --explain` |
| Test task layer | `python test_task_services.py "Health"` |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `address already in use` on 8000 | Server already running; use it, or `lsof -ti :8000 \| xargs kill` |
| Tunnel not in ChatGPT picker | Associate tunnel with your ChatGPT workspace in Platform |
| Connector fails | Keep `tunnel-client run` healthy; run `tunnel-client doctor` |
| Cursor can't connect (HTTP) | Confirm `python mcp_server.py` is running; restart Cursor |
| Google auth errors | Check `token.json`; re-run a task_services test script |

---

## Legacy: Cloudflare quick tunnel

Not recommended now that OpenAI Secure MCP Tunnel exists. If you still use it, set `MCP_PUBLIC_HOST=your-subdomain.trycloudflare.com` and restart `mcp_server.py`. The hostname changes every time you restart `cloudflared`.

---

## Security

- Never commit `.env`, `credentials.json`, or `token.json`.
- Store API keys only in `.env` on your machine.
- If an API key is ever pasted into chat or committed, **rotate it immediately** in OpenAI Platform.
