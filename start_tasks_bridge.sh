#!/usr/bin/env bash
# Start Tasks Bridge MCP server (HTTP) and optional OpenAI tunnel-client for ChatGPT.
#
# Usage:
#   ./start_tasks_bridge.sh              # macOS: three compact Terminal windows (default)
#   ./start_tasks_bridge.sh --windows    # same as default on macOS
#   ./start_tasks_bridge.sh --foreground # MCP + tunnel in this terminal (any OS)
#   ./start_tasks_bridge.sh --windows --no-inspector
#   ./start_tasks_bridge.sh --stop       # stop MCP server (port 8000), tunnel-client, and Inspector
#   ./start_tasks_bridge.sh --status     # check MCP server, tunnel, and Inspector (also --check)
#   ./start_tasks_bridge.sh --http       # HTTP server only
#   ./start_tasks_bridge.sh --tunnel     # tunnel-client only (HTTP must already be running)
#
# Window size (macOS --windows): TASKS_BRIDGE_WINDOW_X/Y/WIDTH/HEIGHT/GAP in .env

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON="$PROJECT_DIR/.venv/bin/python"
TUNNEL_CLIENT="$PROJECT_DIR/tunnel-client"
MCP_URL="http://127.0.0.1:8000/mcp"
PID_DIR="$PROJECT_DIR/.tasks-bridge"
HTTP_PID_FILE="$PID_DIR/mcp-http.pid"
TUNNEL_PID_FILE="$PID_DIR/tunnel-client.pid"
TERMINAL_WINDOW_IDS_FILE="$PID_DIR/terminal-window-ids.txt"

HTTP_WINDOW_TITLE="Tasks Bridge — MCP Server"
TUNNEL_WINDOW_TITLE="Tasks Bridge — Tunnel"
INSPECTOR_WINDOW_TITLE="Tasks Bridge — Inspector"
INSPECTOR_URL="http://127.0.0.1:8000/mcp"

INSPECTOR_URL="http://127.0.0.1:8000/mcp"

MODE=""
INCLUDE_INSPECTOR=1
for arg in "$@"; do
  case "$arg" in
    --http) MODE="http" ;;
    --tunnel) MODE="tunnel" ;;
    --windows) MODE="windows" ;;
    --foreground|--all) MODE="all" ;;
    --stop) MODE="stop" ;;
    --status|--check) MODE="status" ;;
    --no-inspector) INCLUDE_INSPECTOR=0 ;;
  esac
done

if [[ -z "$MODE" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    MODE="windows"
  else
    MODE="all"
  fi
fi

if [[ "${TASKS_BRIDGE_INSPECTOR:-1}" == "0" ]]; then
  INCLUDE_INSPECTOR=0
fi

if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

# Compact Terminal.app windows (macOS --windows). Override in .env if needed.
TERMINAL_WIN_X="${TASKS_BRIDGE_WINDOW_X:-20}"
TERMINAL_WIN_Y="${TASKS_BRIDGE_WINDOW_Y:-40}"
TERMINAL_WIN_WIDTH="${TASKS_BRIDGE_WINDOW_WIDTH:-440}"
TERMINAL_WIN_HEIGHT="${TASKS_BRIDGE_WINDOW_HEIGHT:-260}"
TERMINAL_WIN_GAP="${TASKS_BRIDGE_WINDOW_GAP:-8}"

TUNNEL_PROFILE="${TUNNEL_CLIENT_PROFILE:-tasks-bridge}"
TMUX_SESSION="${TASKS_BRIDGE_TMUX_SESSION:-tasks-bridge}"  # legacy cleanup only

mkdir -p "$PID_DIR"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing virtualenv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

port_in_use() {
  "$PYTHON" - <<'PY'
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("127.0.0.1", 8000))
except OSError:
    raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_port_free() {
  local port="${1:-8000}"
  local tries="${2:-40}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if port_in_use; then
      sleep 0.25
    else
      return 0
    fi
  done
  echo "Warning: port ${port} still in use after ${tries} attempts."
  return 1
}

port_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

pid_listening_on_port() {
  local port="$1"
  lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1
}

proc_label() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    echo "—"
    return
  fi
  ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || echo "PID $pid"
}

mcp_server_pids() {
  pgrep -f "${PROJECT_DIR}/mcp_server.py" 2>/dev/null || pgrep -f "mcp_server.py" 2>/dev/null || true
}

tunnel_client_pids() {
  pgrep -f "tunnel-client run" 2>/dev/null || pgrep -x tunnel-client 2>/dev/null || true
}

inspector_pids() {
  pgrep -f "@modelcontextprotocol/inspector" 2>/dev/null || pgrep -f "inspector-bin" 2>/dev/null || true
}

mcp_responds() {
  curl -sf --max-time 3 -X POST "$MCP_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"status-check","version":"1"}}}' \
    | head -c 1000 | grep -q '"result"'
}

tunnel_linked_to_mcp() {
  local tunnel_pid="$1"
  [[ -z "$tunnel_pid" ]] && return 1
  lsof -nP -a -p "$tunnel_pid" -iTCP:8000 -sTCP:ESTABLISHED >/dev/null 2>&1
}

inspector_ui_responds() {
  curl -sf --max-time 3 "http://127.0.0.1:6274/" >/dev/null 2>&1
}

print_status_line() {
  local label="$1"
  local state="$2"
  local detail="$3"
  printf "  %-10s %s" "$state" "$label"
  if [[ -n "$detail" ]]; then
    printf " — %s" "$detail"
  fi
  printf "\n"
}

print_bridge_status() {
  local mcp_state="DOWN"
  local mcp_detail=""
  local tunnel_state="DOWN"
  local tunnel_detail=""
  local inspector_state="DOWN"
  local inspector_detail=""
  local mcp_ok=0 tunnel_ok=0 inspector_ok=0

  echo "Tasks Bridge status"
  echo "===================="
  echo

  echo "MCP server (Cursor, ChatGPT tunnel, Inspector)"
  local mcp_pid port_pid
  mcp_pid="$(mcp_server_pids | head -1)"
  if port_listening 8000; then
    port_pid="$(pid_listening_on_port 8000)"
    if mcp_responds; then
      mcp_state="UP"
      mcp_ok=1
      mcp_detail="port 8000, initialize ok"
      if [[ -n "$mcp_pid" ]]; then
        mcp_detail="$mcp_detail, PID $mcp_pid"
      elif [[ -n "$port_pid" ]]; then
        mcp_detail="$mcp_detail, listener PID $port_pid ($(proc_label "$port_pid"))"
      fi
    else
      mcp_state="STALE"
      mcp_detail="port 8000 open but MCP initialize failed — restart MCP server"
    fi
  elif [[ -n "$mcp_pid" ]]; then
    mcp_state="STALE"
    mcp_detail="process PID $mcp_pid but port 8000 not listening — restart MCP server"
  else
    mcp_detail="not running — Cursor and ChatGPT cannot reach tasks"
  fi
  print_status_line "HTTP $MCP_URL" "$mcp_state" "$mcp_detail"
  if [[ -n "$mcp_pid" && "$mcp_state" != "DOWN" ]]; then
    echo "             $(proc_label "$mcp_pid")"
  fi
  echo

  echo "ChatGPT tunnel (tunnel-client → MCP server)"
  local tunnel_pid
  tunnel_pid="$(tunnel_client_pids | head -1)"
  if [[ -n "$tunnel_pid" ]]; then
    if port_listening 8000 && mcp_responds; then
      tunnel_state="UP"
      tunnel_ok=1
      if tunnel_linked_to_mcp "$tunnel_pid"; then
        tunnel_detail="PID $tunnel_pid, active connection to localhost:8000"
      else
        tunnel_detail="PID $tunnel_pid, idle — connects on demand when ChatGPT calls"
      fi
    elif port_listening 8000; then
      tunnel_state="STALE"
      tunnel_detail="PID $tunnel_pid running but MCP initialize failed — restart MCP server"
    else
      tunnel_state="STALE"
      tunnel_detail="PID $tunnel_pid running but MCP server is down — restart both"
    fi
  elif [[ -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
    tunnel_state="N/A"
    tunnel_detail="CONTROL_PLANE_API_KEY not set in .env"
    tunnel_ok=1
  elif ! tunnel_client_available; then
    tunnel_state="N/A"
    tunnel_detail="tunnel-client not installed"
    tunnel_ok=1
  else
    tunnel_detail="not running — ChatGPT tunnel connector will not work"
  fi
  print_status_line "tunnel-client (profile: $TUNNEL_PROFILE)" "$tunnel_state" "$tunnel_detail"
  if [[ -n "$tunnel_pid" ]]; then
    echo "             $(proc_label "$tunnel_pid")"
  fi
  echo

  echo "MCP Inspector (dev UI + proxy)"
  local inspector_pid ui_pid proxy_pid
  inspector_pid="$(inspector_pids | head -1)"
  local ui_up=0 proxy_up=0
  port_listening 6274 && ui_up=1
  port_listening 6277 && proxy_up=1

  if [[ "$ui_up" -eq 1 && "$proxy_up" -eq 1 ]]; then
    ui_pid="$(pid_listening_on_port 6274)"
    proxy_pid="$(pid_listening_on_port 6277)"
    if inspector_ui_responds; then
      inspector_state="UP"
      inspector_ok=1
      inspector_detail="UI :6274 + proxy :6277 responding"
    else
      inspector_state="STALE"
      inspector_detail="ports open but UI not responding — restart Inspector"
    fi
    if [[ -n "$inspector_pid" ]]; then
      inspector_detail="$inspector_detail, PID $inspector_pid"
    fi
  elif [[ -n "$inspector_pid" || "$ui_up" -eq 1 || "$proxy_up" -eq 1 ]]; then
    inspector_state="STALE"
    inspector_detail="partial (UI:$([[ $ui_up -eq 1 ]] && echo up || echo down), proxy:$([[ $proxy_up -eq 1 ]] && echo up || echo down)) — restart Inspector"
    [[ -n "$inspector_pid" ]] && inspector_detail="$inspector_detail, PID $inspector_pid"
  else
    inspector_detail="not running — optional for dev; use --windows to start"
    inspector_ok=1
  fi
  print_status_line "Inspector http://127.0.0.1:6274" "$inspector_state" "$inspector_detail"
  if [[ -n "$inspector_pid" ]]; then
    echo "             $(proc_label "$inspector_pid")"
  fi
  echo

  echo "Summary"
  echo "-------"
  if [[ "$mcp_ok" -eq 1 && "$tunnel_ok" -eq 1 && "$inspector_ok" -eq 1 ]]; then
    echo "All checked services look usable."
    if [[ "$inspector_state" == "DOWN" ]]; then
      echo "Inspector is optional; MCP + tunnel are enough for Cursor and ChatGPT."
    fi
  else
    echo "Some services need attention:"
    [[ "$mcp_ok" -eq 0 ]] && echo "  • MCP server: ./start_tasks_bridge.sh   (macOS) or --http"
    [[ "$tunnel_state" == "STALE" || "$tunnel_state" == "DOWN" ]] && \
      [[ -n "${CONTROL_PLANE_API_KEY:-}" ]] && tunnel_client_available && \
      echo "  • Tunnel: ./start_tasks_bridge.sh --tunnel   (if MCP is already UP)"
    [[ "$inspector_state" == "STALE" || "$inspector_state" == "DOWN" ]] && \
      echo "  • Inspector: included when you run ./start_tasks_bridge.sh (macOS default)"
    if [[ "$mcp_ok" -eq 0 || "$tunnel_state" != "UP" && "$tunnel_state" != "N/A" ]]; then
      echo "  • After sleep or multiple failures: ./start_tasks_bridge.sh"
    fi
  fi
  echo

  if [[ "$mcp_ok" -eq 0 ]]; then
    return 1
  fi
  if [[ -n "${CONTROL_PLANE_API_KEY:-}" ]] && tunnel_client_available && [[ "$tunnel_ok" -eq 0 ]]; then
    return 1
  fi
  return 0
}

start_http_server() {
  stop_http_server
  sleep 0.5

  echo "Starting HTTP MCP server at $MCP_URL"
  "$PYTHON" "$PROJECT_DIR/mcp_server.py" &
  echo $! >"$HTTP_PID_FILE"

  for _ in {1..20}; do
    if port_in_use; then
      echo "HTTP MCP server ready."
      return 0
    fi
    sleep 0.25
  done

  echo "HTTP MCP server failed to start. Check output above."
  exit 1
}

start_tunnel_client() {
  local tunnel_client=""
  tunnel_client="$(resolve_tunnel_client)" || {
    echo "tunnel-client not found."
    echo "Install it to PATH or to: $TUNNEL_CLIENT"
    echo "Download: https://github.com/openai/tunnel-client/releases"
    echo "See docs/chatgpt-tunnel.md"
    exit 1
  }

  if [[ -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
    echo "CONTROL_PLANE_API_KEY is not set in .env"
    exit 1
  fi

  export CONTROL_PLANE_API_KEY

  echo "Checking tunnel profile: $TUNNEL_PROFILE"
  if ! "$tunnel_client" doctor --profile "$TUNNEL_PROFILE" --explain; then
    echo
    echo "Warning: doctor reported issues. If the only failure is oauth_metadata,"
    echo "that is expected for this read-only server (no OAuth configured)."
    echo "Continuing to start tunnel-client..."
    echo
  fi

  echo "Starting tunnel-client (profile: $TUNNEL_PROFILE)"
  echo "Keep this running for ChatGPT. Connect in ChatGPT: Settings → Connectors → Connection: Tunnel"
  exec "$tunnel_client" run --profile "$TUNNEL_PROFILE"
}

tunnel_client_available() {
  command -v tunnel-client >/dev/null 2>&1 || [[ -x "$TUNNEL_CLIENT" ]]
}

resolve_tunnel_client() {
  if command -v tunnel-client >/dev/null 2>&1; then
    echo "tunnel-client"
  elif [[ -x "$TUNNEL_CLIENT" ]]; then
    echo "$TUNNEL_CLIENT"
  else
    return 1
  fi
}

stop_http_server() {
  local stopped=0

  if pgrep -f "${PROJECT_DIR}/mcp_server.py" >/dev/null 2>&1; then
    pkill -f "${PROJECT_DIR}/mcp_server.py" 2>/dev/null || true
    echo "Stopped mcp_server.py."
    stopped=1
  elif pgrep -f "mcp_server.py" >/dev/null 2>&1; then
    pkill -f "mcp_server.py" 2>/dev/null || true
    echo "Stopped mcp_server.py."
    stopped=1
  fi

  if port_in_use; then
    lsof -ti :8000 | xargs kill 2>/dev/null || true
    echo "Stopped MCP HTTP server on port 8000."
    stopped=1
  fi

  rm -f "$HTTP_PID_FILE"
  if [[ "$stopped" -eq 1 ]]; then
    return 0
  fi
  return 1
}

stop_tunnel_client() {
  local stopped=0

  if pgrep -f "tunnel-client run" >/dev/null 2>&1; then
    pkill -f "tunnel-client run" 2>/dev/null || true
    echo "Stopped tunnel-client."
    stopped=1
  elif pgrep -x tunnel-client >/dev/null 2>&1; then
    pkill -x tunnel-client 2>/dev/null || true
    echo "Stopped tunnel-client."
    stopped=1
  fi

  rm -f "$TUNNEL_PID_FILE"
  if [[ "$stopped" -eq 1 ]]; then
    return 0
  fi
  return 1
}

stop_inspector() {
  local stopped=0

  if pgrep -f "@modelcontextprotocol/inspector" >/dev/null 2>&1; then
    pkill -f "@modelcontextprotocol/inspector" 2>/dev/null || true
    echo "Stopped MCP Inspector."
    stopped=1
  elif pgrep -f "inspector-bin" >/dev/null 2>&1; then
    pkill -f "inspector-bin" 2>/dev/null || true
    echo "Stopped MCP Inspector."
    stopped=1
  fi

  for port in 6274 6277; do
    if lsof -ti :"$port" >/dev/null 2>&1; then
      lsof -ti :"$port" | xargs kill 2>/dev/null || true
      echo "Stopped MCP Inspector on port $port."
      stopped=1
    fi
  done

  if [[ "$stopped" -eq 1 ]]; then
    return 0
  fi
  return 1
}

close_bridge_terminal_windows() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return 0
  fi

  local closed_count=0
  local extra_closed=0

  if [[ -f "$TERMINAL_WINDOW_IDS_FILE" ]]; then
    while IFS= read -r wid; do
      [[ -z "$wid" ]] && continue
      if osascript <<OSA 2>/dev/null
tell application "Terminal"
  try
    close (every window whose id is $wid) saving no
  end try
end tell
OSA
      then
        closed_count=$((closed_count + 1))
      fi
    done <"$TERMINAL_WINDOW_IDS_FILE"
    rm -f "$TERMINAL_WINDOW_IDS_FILE"
  fi

  extra_closed="$(osascript <<'OSA' 2>/dev/null || echo 0
tell application "Terminal"
  set closedCount to 0
  repeat with w in windows
    try
      set tabTitle to custom title of front tab of w
      if tabTitle starts with "Tasks Bridge" then
        close w saving no
        set closedCount to closedCount + 1
      end if
    end try
  end repeat
  return closedCount
end tell
OSA
)"
  closed_count=$((closed_count + extra_closed))

  if [[ "$closed_count" -gt 0 ]]; then
    if [[ "$closed_count" -eq 1 ]]; then
      echo "Closed Tasks Bridge Terminal window."
    else
      echo "Closed ${closed_count} Tasks Bridge Terminal window(s)."
    fi
  fi
}

stop_tmux_session() {
  if ! command -v tmux >/dev/null 2>&1; then
    return 1
  fi
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
    echo "Stopped tmux session ${TMUX_SESSION}."
    return 0
  fi
  return 1
}

stop_bridge() {
  local stopped=0

  stop_tmux_session && stopped=1 || true
  stop_http_server && stopped=1 || true
  stop_tunnel_client && stopped=1 || true
  stop_inspector && stopped=1 || true
  if [[ "$stopped" -eq 1 ]]; then
    sleep 0.4
  fi
  close_bridge_terminal_windows

  if [[ "$stopped" -eq 0 ]]; then
    echo "Nothing was running."
  fi
}

prepare_bridge_service_launchers() {
  local tunnel_client
  tunnel_client="$(resolve_tunnel_client)" || {
    echo "tunnel-client not found."
    echo "Install it to PATH or to: $TUNNEL_CLIENT"
    exit 1
  }

  if [[ -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
    echo "CONTROL_PLANE_API_KEY is not set in .env"
    exit 1
  fi

  stop_bridge
  sleep 0.5
  wait_for_port_free 8000 || true

  local http_launcher="$PID_DIR/start-http-terminal.sh"
  local tunnel_launcher="$PID_DIR/start-tunnel-terminal.sh"
  local inspector_launcher="$PID_DIR/start-inspector-terminal.sh"

  cat >"$http_launcher" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
printf '\033]0;%s\007' "$HTTP_WINDOW_TITLE"
cd $(printf '%q' "$PROJECT_DIR")
echo "$HTTP_WINDOW_TITLE"
echo "URL: $MCP_URL"
echo "Leave this window open while using Cursor or ChatGPT."
echo
$(printf '%q' "$PYTHON") $(printf '%q' "$PROJECT_DIR/mcp_server.py")
SCRIPT

  cat >"$tunnel_launcher" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
printf '\033]0;%s\007' "$TUNNEL_WINDOW_TITLE"
cd $(printf '%q' "$PROJECT_DIR")
set -a
# shellcheck disable=SC1091
source $(printf '%q' "$PROJECT_DIR/.env")
set +a
export CONTROL_PLANE_API_KEY

echo "$TUNNEL_WINDOW_TITLE"
echo "Profile: $TUNNEL_PROFILE"
echo "Waiting for MCP HTTP server on port 8000..."
for _ in \$(seq 1 40); do
  if $(printf '%q' "$PYTHON") - <<'PY'
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.2)
raise SystemExit(0 if sock.connect_ex(("127.0.0.1", 8000)) == 0 else 1)
PY
  then
    break
  fi
  sleep 0.25
done

echo "Starting tunnel-client..."
echo "Expected noise: oauth_metadata warnings and one 400 probe are normal."
echo
$(printf '%q' "$tunnel_client") run --profile $(printf '%q' "$TUNNEL_PROFILE")
SCRIPT

  if [[ "$INCLUDE_INSPECTOR" -eq 1 ]]; then
    if ! command -v npx >/dev/null 2>&1; then
      echo "npx not found; skipping MCP Inspector. Install Node.js or pass --no-inspector."
      INCLUDE_INSPECTOR=0
    else
      cat >"$inspector_launcher" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
printf '\033]0;%s\007' "$INSPECTOR_WINDOW_TITLE"
cd $(printf '%q' "$PROJECT_DIR")
echo "$INSPECTOR_WINDOW_TITLE"
echo "Server URL preset: $INSPECTOR_URL (Streamable HTTP via proxy)"
echo "Waiting for MCP HTTP server on port 8000..."
for _ in \$(seq 1 40); do
  if $(printf '%q' "$PYTHON") - <<'PY'
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.2)
raise SystemExit(0 if sock.connect_ex(("127.0.0.1", 8000)) == 0 else 1)
PY
  then
    break
  fi
  sleep 0.25
done

echo "Starting MCP Inspector (fresh proxy + browser tab)..."
echo "Close old Inspector browser tabs; they keep stale proxy auth tokens."
echo
export MCP_AUTO_OPEN_ENABLED=true
npx -y @modelcontextprotocol/inspector --transport http --server-url $(printf '%q' "$INSPECTOR_URL")
SCRIPT
    fi
  fi

  chmod +x "$http_launcher" "$tunnel_launcher"
  if [[ "$INCLUDE_INSPECTOR" -eq 1 ]]; then
    chmod +x "$inspector_launcher"
  fi

  HTTP_LAUNCHER="$http_launcher"
  TUNNEL_LAUNCHER="$tunnel_launcher"
  INSPECTOR_LAUNCHER="$inspector_launcher"
}

launch_mac_terminal_windows() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Separate Terminal windows are macOS only."
    echo "Use ./start_tasks_bridge.sh --http and --tunnel in separate terminals."
    echo "See docs/local-dev.md#platform-support"
    exit 1
  fi

  prepare_bridge_service_launchers

  local http_launcher_as tunnel_launcher_as inspector_launcher_as
  local http_title_as tunnel_title_as inspector_title_as window_ids
  local win_x win_y win_w win_h win_gap
  local mcp_bounds tunnel_bounds inspector_bounds
  win_x="$TERMINAL_WIN_X"
  win_y="$TERMINAL_WIN_Y"
  win_w="$TERMINAL_WIN_WIDTH"
  win_h="$TERMINAL_WIN_HEIGHT"
  win_gap="$TERMINAL_WIN_GAP"
  mcp_bounds="{${win_x}, ${win_y}, $((win_x + win_w)), $((win_y + win_h))}"
  tunnel_bounds="{${win_x}, $((win_y + win_h + win_gap)), $((win_x + win_w)), $((win_y + 2 * win_h + win_gap))}"
  inspector_bounds="{${win_x}, $((win_y + 2 * (win_h + win_gap))), $((win_x + win_w)), $((win_y + 3 * win_h + 2 * win_gap))}"

  http_launcher_as="$(printf '%s' "$HTTP_LAUNCHER" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  tunnel_launcher_as="$(printf '%s' "$TUNNEL_LAUNCHER" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  http_title_as="$(printf '%s' "$HTTP_WINDOW_TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  tunnel_title_as="$(printf '%s' "$TUNNEL_WINDOW_TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')"

  if [[ "$INCLUDE_INSPECTOR" -eq 1 ]]; then
    inspector_launcher_as="$(printf '%s' "$INSPECTOR_LAUNCHER" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    inspector_title_as="$(printf '%s' "$INSPECTOR_WINDOW_TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    window_ids="$(osascript <<OSA
tell application "Terminal"
  activate
  set httpLauncher to "$http_launcher_as"
  set tunnelLauncher to "$tunnel_launcher_as"
  set inspectorLauncher to "$inspector_launcher_as"
  set mcpTab to do script "bash " & quoted form of httpLauncher
  set custom title of mcpTab to "$http_title_as"
  delay 0.2
  set bounds of front window to $mcp_bounds
  set httpWindowId to id of front window
  delay 0.4
  set tunnelTab to do script "bash " & quoted form of tunnelLauncher
  set custom title of tunnelTab to "$tunnel_title_as"
  delay 0.2
  set bounds of front window to $tunnel_bounds
  set tunnelWindowId to id of front window
  delay 0.4
  set inspectorTab to do script "bash " & quoted form of inspectorLauncher
  set custom title of inspectorTab to "$inspector_title_as"
  delay 0.2
  set bounds of front window to $inspector_bounds
  set inspectorWindowId to id of front window
  return (httpWindowId as text) & linefeed & (tunnelWindowId as text) & linefeed & (inspectorWindowId as text)
end tell
OSA
)" || {
      echo "Failed to open Terminal windows."
      stop_bridge
      exit 1
    }
  else
    window_ids="$(osascript <<OSA
tell application "Terminal"
  activate
  set httpLauncher to "$http_launcher_as"
  set tunnelLauncher to "$tunnel_launcher_as"
  set mcpTab to do script "bash " & quoted form of httpLauncher
  set custom title of mcpTab to "$http_title_as"
  delay 0.2
  set bounds of front window to $mcp_bounds
  set httpWindowId to id of front window
  delay 0.4
  set tunnelTab to do script "bash " & quoted form of tunnelLauncher
  set custom title of tunnelTab to "$tunnel_title_as"
  delay 0.2
  set bounds of front window to $tunnel_bounds
  set tunnelWindowId to id of front window
  return (httpWindowId as text) & linefeed & (tunnelWindowId as text)
end tell
OSA
)" || {
      echo "Failed to open Terminal windows."
      stop_bridge
      exit 1
    }
  fi

  printf '%s\n' "$window_ids" >"$TERMINAL_WINDOW_IDS_FILE"

  if [[ "$INCLUDE_INSPECTOR" -eq 1 ]]; then
    echo "Opened three compact Terminal windows (${win_w}x${win_h}, stacked):"
    echo "  1. $HTTP_WINDOW_TITLE"
    echo "  2. $TUNNEL_WINDOW_TITLE"
    echo "  3. $INSPECTOR_WINDOW_TITLE"
  else
    echo "Opened two compact Terminal windows (${win_w}x${win_h}, stacked):"
    echo "  1. $HTTP_WINDOW_TITLE"
    echo "  2. $TUNNEL_WINDOW_TITLE"
  fi
  echo
  echo "Resize via .env: TASKS_BRIDGE_WINDOW_WIDTH, TASKS_BRIDGE_WINDOW_HEIGHT, TASKS_BRIDGE_WINDOW_X, TASKS_BRIDGE_WINDOW_Y, TASKS_BRIDGE_WINDOW_GAP"
  echo "Switch windows with Cmd+\` or the Window menu — no special key chords."
  echo "Look for: mcp session initialized and tunnel-client started."
  if [[ "$INCLUDE_INSPECTOR" -eq 1 ]]; then
    echo "Inspector opens a browser tab (close old Inspector tabs if reconnecting)."
  fi
}

case "$MODE" in
  stop)
    stop_bridge
    ;;
  status)
    print_bridge_status || exit 1
    ;;
  windows)
    launch_mac_terminal_windows
    ;;
  http)
    start_http_server
    echo "Done. Cursor can use: $MCP_URL"
    ;;
  tunnel)
    stop_tunnel_client
    sleep 0.5
    if port_in_use; then
      :
    else
      echo "HTTP MCP server is not running on port 8000."
      echo "Start it first: ./start_tasks_bridge.sh --http"
      exit 1
    fi
    start_tunnel_client
    ;;
  all)
    start_http_server
    if [[ -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
      echo
      echo "HTTP server is up for Cursor at $MCP_URL"
      echo "ChatGPT tunnel not started: CONTROL_PLANE_API_KEY missing from .env"
      wait "$(cat "$HTTP_PID_FILE")"
    elif ! tunnel_client_available; then
      echo
      echo "HTTP server is up for Cursor at $MCP_URL"
      echo "ChatGPT tunnel not started: tunnel-client is not installed."
      echo "Download: https://github.com/openai/tunnel-client/releases"
      echo "Or place the binary at: $TUNNEL_CLIENT"
      wait "$(cat "$HTTP_PID_FILE")"
    else
      start_tunnel_client
    fi
    ;;
esac
