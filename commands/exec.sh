#!/bin/bash
# =============================================================================
# nano-whale :: commands/exec.sh
# Exec into container (in-shell and new window)
# =============================================================================

# ---------------------------------------------------------------------------
# Exec into container (takes over the terminal)
# ---------------------------------------------------------------------------
handle_exec_container() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"

  if [[ -z "$name" || "$state" != "running" ]]; then
    set_notify "Container must be running" "red"
    return
  fi

  NW_FULLSCREEN=true
  stop_log_stream
  stop_stats_stream

  # Restore terminal for interactive use
  tui_restore

  printf '\n🐳 Entering shell in %s...\n📋 Press Ctrl+D to return\n📍 Container path: '
  $DOCKER_CMD exec "$name" sh -c 'pwd' 2>/dev/null || printf '/\n'
  printf '\n'

  # Use an explicit interactive prompt so the container path remains visible
  # even when the image has no shell profile or prompt configuration.
  $DOCKER_CMD exec -it "$name" sh -c '
    export PS1="\u@\h:\w\$ "
    if [ -x /bin/bash ]; then
      exec /bin/bash --noprofile --norc -i
    else
      exec /bin/sh -i
    fi
  ' 2>/dev/null || true

  printf '\n🐳 Returned from %s\n' "$name"
  sleep 0.3

  # Restore TUI
  NW_FULLSCREEN=false
  tui_init
  update_term_size
  calc_layout
  fetch_all
  start_stats_stream

  # Restart log stream if we were on the logs tab
  if (( NW_CURRENT_TAB == 0 )); then
    local cur="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
    [[ -n "$cur" ]] && start_log_stream "$cur" 100
  fi
}

# ---------------------------------------------------------------------------
# Exec in a new terminal window
# ---------------------------------------------------------------------------
handle_exec_new_window() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"

  if [[ -z "$name" || "$state" != "running" ]]; then
    set_notify "Container must be running" "red"
    return
  fi

  local cmd="$DOCKER_CMD exec -it $(shell_quote "$name") sh -c 'exec /bin/bash 2>/dev/null || exec /bin/sh'"
  spawn_new_window "$cmd" "exec-$name"
}

# ---------------------------------------------------------------------------
# Spawn a command in a new terminal window (cross-platform)
# ---------------------------------------------------------------------------
spawn_new_window() {
  local cmd="$1"
  local label="$2"

  case "$NW_PLATFORM" in
    darwin)
      osascript -e "tell application \"Terminal\" to do script \"$cmd\"" 2>/dev/null \
        && set_notify "Opened new Terminal window" "green" \
        || set_notify "Failed to open Terminal" "red"
      ;;
    linux)
      # Try common terminal emulators
      if command_exists x-terminal-emulator; then
        x-terminal-emulator -e bash -lc "$cmd" &
        set_notify "Opened new terminal window" "green"
      elif command_exists gnome-terminal; then
        gnome-terminal -- bash -c "$cmd; exec bash" &
        set_notify "Opened new terminal window" "green"
      elif command_exists xterm; then
        xterm -e bash -lc "$cmd" &
        set_notify "Opened new terminal window" "green"
      elif command_exists konsole; then
        konsole -e bash -lc "$cmd" &
        set_notify "Opened new terminal window" "green"
      else
        set_notify "No terminal found. Run: $cmd" "yellow"
      fi
      ;;
    *)
      set_notify "New window not supported on $NW_PLATFORM" "yellow"
      ;;
  esac
}
