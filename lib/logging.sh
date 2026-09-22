#!/bin/bash
# =============================================================================
# nano-whale :: lib/logging.sh
# Log formatting helpers for the Logs tab
# =============================================================================

# ---------------------------------------------------------------------------
# Start streaming logs for a container in background
# ---------------------------------------------------------------------------
start_log_stream() {
  local name="$1"
  local tail="${2:-100}"

  stop_log_stream

  NW_LOGS_CONTAINER="$name"
  NW_LOGS_CONTENT=""
  NW_LOGS_PENDING=true

  _NW_LOGS_FIFO=$(mktemp /tmp/nw-logs.XXXXXX)
  _NW_TMPFILES+=("$_NW_LOGS_FIFO")

  (
    $DOCKER_CMD logs -f --tail "$tail" "$name" > "$_NW_LOGS_FIFO" 2>&1
  ) &
  _NW_LOGS_PID=$!
}

# ---------------------------------------------------------------------------
# Stop log stream
# ---------------------------------------------------------------------------
stop_log_stream() {
  if [[ -n "${_NW_LOGS_PID:-}" ]] && kill -0 "$_NW_LOGS_PID" 2>/dev/null; then
    kill "$_NW_LOGS_PID" 2>/dev/null || true
  fi
  _NW_LOGS_PID=""
  NW_LOGS_CONTAINER=""
  NW_LOGS_PENDING=false
}

# ---------------------------------------------------------------------------
# Read new log lines from the fifo
# ---------------------------------------------------------------------------
read_logs() {
  [[ -z "${_NW_LOGS_FIFO:-}" ]] && return
  [[ ! -f "$_NW_LOGS_FIFO" ]] && return

  local content
  content=$(tail -n "${NW_LOGS_MAX_LINES:-500}" "$_NW_LOGS_FIFO" 2>/dev/null) || return

  [[ -z "$content" ]] && return
  [[ "$content" == "$NW_LOGS_CONTENT" ]] && return

  NW_LOGS_CONTENT="$content"
  NW_LOGS_PENDING=false
  NW_DATA_CHANGED=true
}

# ---------------------------------------------------------------------------
# Get the last N lines of log content for display
# ---------------------------------------------------------------------------
get_log_display_lines() {
  local max_lines="$1"
  if [[ -z "$NW_LOGS_CONTENT" ]]; then
    echo "No logs yet..."
    return
  fi

  local -a lines=()
  mapfile -t lines <<< "$NW_LOGS_CONTENT"
  local count=${#lines[@]}
  local start=0
  (( count > max_lines )) && start=$(( count - max_lines ))

  local i
  for (( i=start; i<count; i++ )); do
    printf '%s\n' "${lines[$i]}"
  done
}
