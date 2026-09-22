#!/bin/bash
# =============================================================================
# nano-whale :: lib/stats.sh
# Docker stats streaming via background process
# =============================================================================

# ---------------------------------------------------------------------------
# Start stats streaming in background
# Writes stats data to a temp file that the main loop reads
# ---------------------------------------------------------------------------
start_stats_stream() {
  stop_stats_stream

  _NW_STATS_FIFO=$(mktemp /tmp/nw-stats.XXXXXX)
  _NW_TMPFILES+=("$_NW_STATS_FIFO")

  (
    while true; do
      # Run docker stats with --no-stream to get one snapshot
      output=""
      output=$($DOCKER_CMD stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}|{{.PIDs}}' 2>/dev/null)

      if [[ -n "$output" ]]; then
        printf '%s\n' "$output" > "$_NW_STATS_FIFO"
      fi

      sleep "${NW_STATS_INTERVAL:-2}"
    done
  ) &
  _NW_STATS_PID=$!
}

# ---------------------------------------------------------------------------
# Stop stats stream
# ---------------------------------------------------------------------------
stop_stats_stream() {
  if [[ -n "${_NW_STATS_PID:-}" ]] && kill -0 "$_NW_STATS_PID" 2>/dev/null; then
    kill "$_NW_STATS_PID" 2>/dev/null || true
  fi
  _NW_STATS_PID=""
}

# ---------------------------------------------------------------------------
# Read latest stats from the temp file and update state
# ---------------------------------------------------------------------------
read_stats() {
  [[ -z "${_NW_STATS_FIFO:-}" ]] && return
  [[ ! -f "$_NW_STATS_FIFO" ]] && return

  local content
  content=$(cat "$_NW_STATS_FIFO" 2>/dev/null) || return
  [[ -z "$content" ]] && return
  [[ "$content" == "${_NW_STATS_LAST_CONTENT:-}" ]] && return
  _NW_STATS_LAST_CONTENT="$content"
  NW_DATA_CHANGED=true

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local name cpu_str mem_str mem_usage net_io block_io pids
    IFS='|' read -r name cpu_str mem_str mem_usage net_io block_io pids <<< "$line"

    [[ -z "$name" ]] && continue

    # Strip % from cpu and mem
    local cpu="${cpu_str//%/}"
    local mem="${mem_str//%/}"

    STAT_CPU["$name"]="$cpu"
    STAT_MEM["$name"]="$mem"
    STAT_MEM_USAGE["$name"]="${mem_usage:-N/A}"
    STAT_NET_IO["$name"]="${net_io:-N/A}"
    STAT_BLOCK_IO["$name"]="${block_io:-N/A}"
    STAT_PIDS["$name"]="${pids:-N/A}"

    # Push to history
    history_push CPU_HISTORY["$name"] "$cpu"
    history_push MEM_HISTORY["$name"] "$mem"
  done <<< "$content"
}
