# ChatGPT tool discovery

When you add or change MCP tools, the server and MCP Inspector may show the new tool immediately while ChatGPT lags. This document helps distinguish **server issues** from **OpenAI-side propagation delay**.

## Quick checks

1. Call `get_bridge_diagnostics` — confirm `server_version` and `tool_names` on the server.
2. Compare with MCP Inspector's tools list.
3. Click **Refresh** in ChatGPT connector settings, then start a **new** plugin-enabled conversation.
4. If the server shows the new tool but ChatGPT does not, wait and retry Refresh — this is usually propagation lag (case 3 below).

## Failure-layer matrix

| Observation | Likely failing layer |
|---|---|
| Refresh produces **no** server `initialize` / `tools/list` | OpenAI refresh / scan initiation |
| ChatGPT **does** request `tools/list`, but server returns **old** `schema_hash` | Wrong or stale MCP process |
| Server returns **new** `schema_hash`, but ChatGPT still exposes **old** tools | OpenAI registry / catalog propagation |

## Observation protocol (detailed debugging)

Use this when adding a **new MCP tool** and you need to record where discovery breaks.

### Fields to record

| # | Field | How to capture |
|---|---|---|
| 1 | **Server restarted at** | `.tasks-bridge/server-restart.json` → `restarted_at` |
| 2 | **New tool name + expected schema hash** | Bump `SERVER_VERSION` in `bridge_diagnostics.py`; note hash from Inspector or `get_bridge_diagnostics` |
| 3 | **Inspector first saw new tool at** | Inspector tools/list UI timestamp, or `discovery-timeline.jsonl` with `client_name` like `inspector-client` |
| 4 | **ChatGPT Refresh clicked at** | Manual note |
| 5 | **Refresh caused server traffic?** | MCP server log or `.tasks-bridge/discovery-timeline.jsonl`: any `initialize` / `tools/list` after step 4? |
| 6 | **Schema hash ChatGPT received** | `schema_hash` from post-Refresh `tools/list` log line (if any) |
| 7 | **ChatGPT first exposed tool at** | When plugin UI or a new conversation can call the tool |

### Procedure

1. Bump `SERVER_VERSION` and add the tool; restart the MCP server.
2. Confirm new schema in Inspector + `get_bridge_diagnostics`.
3. Click **Refresh** in ChatGPT connector settings.
4. Inspect timeline: `grep mcp_discovery .tasks-bridge/discovery-timeline.jsonl | tail -20`
5. Compare post-Refresh `schema_hash` to expected.
6. Open a **new** plugin-enabled conversation and check action toggles.

### Why Refresh matters

MCP `tools/list_changed` notifications are **not enabled** (`listChanged: false`; stateless HTTP). Treat Refresh plus a new conversation as required per current OpenAI connector behavior.

## Related

- [chatgpt-tunnel.md](chatgpt-tunnel.md) — local tunnel setup
- [railway.md](railway.md) — production HTTPS URL for ChatGPT
