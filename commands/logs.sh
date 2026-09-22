#!/bin/bash
# =============================================================================
# nano-whale :: commands/logs.sh
# Fullscreen logs mode
# =============================================================================

# ---------------------------------------------------------------------------
# Fullscreen live logs (takes over the terminal)
# ---------------------------------------------------------------------------
handle_fullscreen_logs() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"

  if [[ -z "$name" || "$state" != "running" ]]; then
    set_notify "Container must be running" "red"
    return
  fi

  NW_FULLSCREEN=true
  stop_log_stream
  stop_stats_stream

  # Restore terminal for direct output
  tui_restore

  printf '\n🐳 Streaming logs for %s...\n📋 Press Ctrl+D or Ctrl+C to return\n\n' "$name"
  stty -echo -icanon min 0 time 0 2>/dev/null || true

  # Keep log streaming separate from stdin so Ctrl+D can return cleanly.
  $DOCKER_CMD logs -f "$name" 2>&1 &
  local logs_pid=$!
  local log_key=""
  while kill -0 "$logs_pid" 2>/dev/null; do
    if IFS= read -rsn1 -t 0.1 log_key; then
      case "$log_key" in
        $'\004'|$'\003')
          kill "$logs_pid" 2>/dev/null || true
          break
          ;;
      esac
    fi
  done
  wait "$logs_pid" 2>/dev/null || true

  printf '\n🐳 Returned from logs\n'
  sleep 0.3

  # Restore TUI
  NW_FULLSCREEN=false
  tui_init
  update_term_size
  calc_layout
  fetch_all
  start_stats_stream

  # Restart log stream for the tab
  if (( NW_CURRENT_TAB == 0 )); then
    local cur="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
    [[ -n "$cur" ]] && start_log_stream "$cur" 100
  fi
}

# ---------------------------------------------------------------------------
# Logs in a new terminal window
# ---------------------------------------------------------------------------
handle_logs_new_window() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"

  if [[ -z "$name" || "$state" != "running" ]]; then
    set_notify "Container must be running" "red"
    return
  fi

  local cmd="$DOCKER_CMD logs -f $(shell_quote "$name")"
  spawn_new_window "$cmd" "logs-$name"
}
