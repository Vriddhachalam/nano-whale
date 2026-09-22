#!/bin/bash
# =============================================================================
# nano-whale — Lightweight Docker TUI (Bash Edition)
#
# A terminal user interface for managing Docker containers, images,
# volumes, and networks. Pure Bash + ANSI escape codes.
#
# Usage:  ./nano-whale.sh [--help|--version]
# =============================================================================
set -Eo pipefail

# ---------------------------------------------------------------------------
# Resolve script directory (works with symlinks)
# ---------------------------------------------------------------------------
NW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Source all modules
# ---------------------------------------------------------------------------
source "$NW_DIR/config/defaults.sh"
source "$NW_DIR/lib/utils.sh"
source "$NW_DIR/lib/config.sh"
source "$NW_DIR/lib/core.sh"
source "$NW_DIR/lib/tui.sh"
source "$NW_DIR/lib/charts.sh"
source "$NW_DIR/lib/docker.sh"
source "$NW_DIR/lib/actions.sh"
source "$NW_DIR/lib/stats.sh"
source "$NW_DIR/lib/logging.sh"
source "$NW_DIR/lib/input.sh"
source "$NW_DIR/commands/exec.sh"
source "$NW_DIR/commands/logs.sh"
source "$NW_DIR/commands/inspect.sh"
source "$NW_DIR/commands/batch.sh"

# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------
case "${1:-}" in
  --help|-h)
    cat <<'EOF'
🐳 nano-whale — Lightweight Docker TUI (Bash Edition)

USAGE
    nano-whale [OPTIONS]

OPTIONS
    --help, -h       Show this help message
    --version, -v    Show version

KEYBOARD SHORTCUTS
    Navigation:
      Tab          Switch focus between lists
      ↑/↓          Navigate items
      PageUp/Down  Scroll content faster
      Home/End     Jump to top/bottom
      ←/→          Cycle tabs (Logs, Stats, Env, Config, Top)
      2/3/4/5      Focus Containers/Images/Volumes/Networks

    Actions:
      s            Start/Stop container
      r            Restart container
      d            Delete (Container/Image/Volume/Network)
      m            Mark/Unmark item for batch operations
      Ctrl+A       Select/Deselect all items
      t            Exec into container shell
      Ctrl+T       Exec in new terminal window
      l            Fullscreen live logs
      Ctrl+L       Logs in new terminal window
      a            Toggle auto-scroll (Logs)
      F5           Manual refresh
      q            Quit

REQUIREMENTS
    bash 4.3+, docker

OPTIONAL
    jq   (for formatted container inspection)
EOF
    exit 0
    ;;
  --version|-v)
    echo "nano-whale $NW_VERSION"
    exit 0
    ;;
  "")
    ;;  # no args — start TUI
  *)
    die "Unknown option: $1. Use --help for usage."
    ;;
esac

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
  die "nano-whale requires Bash 4.3 or later (found ${BASH_VERSION})"
fi

init_config

# ---------------------------------------------------------------------------
# Welcome screen
# ---------------------------------------------------------------------------
tui_welcome

# ---------------------------------------------------------------------------
# Setup exit trap
# ---------------------------------------------------------------------------
trap _nw_cleanup EXIT
trap 'NW_RUNNING=false' INT TERM
trap 'update_term_size; calc_layout; NW_NEEDS_CLEAR=true; NW_NEEDS_RENDER=true' WINCH

# ---------------------------------------------------------------------------
# Initialize TUI
# ---------------------------------------------------------------------------
NW_HOSTNAME="$(hostname 2>/dev/null || printf 'localhost')"
NW_NEEDS_CLEAR=true
tui_init
update_term_size
calc_layout

# Start background processes
start_data_streams
start_stats_stream

# Let the first background Docker snapshots publish before entering the UI.
# This is bounded so a slow/unavailable daemon never blocks startup.
for (( _nw_startup_poll=0; _nw_startup_poll<20; _nw_startup_poll++ )); do
  fetch_all
  if (( ${#CONT_NAMES[@]} > 0 || ${#IMG_REPOS[@]} > 0 || ${#VOL_NAMES[@]} > 0 || ${#NET_NAMES[@]} > 0 )); then
    break
  fi
  sleep 0.05
done

# ---------------------------------------------------------------------------
# Render the full UI
# ---------------------------------------------------------------------------
render_ui() {
  NW_RENDER_PARTS=()
  tui_begin_update

  # Clear screen
  tui_clear

  # === LEFT PANEL ===

  # Device box
  tui_box "$DEVICE_ROW" 1 "$DEVICE_H" "$LEFT_W" "[1]-Device" "cyan"
  tui_text $(( DEVICE_ROW + 1 )) 2 " $NW_HOSTNAME" "cyan"

  # Containers box
  local cont_label="[2]-Containers (${#CONT_NAMES[@]})"
  tui_box "$CONT_ROW" 1 "$CONT_H" "$LEFT_W" "$cont_label" "green"
  local -a cont_display
  format_containers cont_display
  tui_render_list "$CONT_ROW" 1 "$CONT_H" "$LEFT_W" cont_display "$NW_SEL_CONTAINER" $(( NW_FOCUS == 0 ? 1 : 0 )) "green"

  # Images box
  local img_label="[3]-Images (${#IMG_REPOS[@]})"
  tui_box "$IMG_ROW" 1 "$IMG_H" "$LEFT_W" "$img_label" "yellow"
  local -a img_display
  format_images img_display "$LEFT_W"
  tui_render_list "$IMG_ROW" 1 "$IMG_H" "$LEFT_W" img_display "$NW_SEL_IMAGE" $(( NW_FOCUS == 1 ? 1 : 0 )) "yellow"

  # Volumes box
  local vol_label="[4]-Volumes (${#VOL_NAMES[@]})"
  tui_box "$VOL_ROW" 1 "$VOL_H" "$LEFT_W" "$vol_label" "magenta"
  local -a vol_display
  format_volumes vol_display "$LEFT_W"
  tui_render_list "$VOL_ROW" 1 "$VOL_H" "$LEFT_W" vol_display "$NW_SEL_VOLUME" $(( NW_FOCUS == 2 ? 1 : 0 )) "magenta"

  # Networks box
  local net_label="[5]-Networks (${#NET_NAMES[@]})"
  tui_box "$NET_ROW" 1 "$NET_H" "$LEFT_W" "$net_label" "blue"
  local -a net_display
  format_networks net_display "$LEFT_W"
  tui_render_list "$NET_ROW" 1 "$NET_H" "$LEFT_W" net_display "$NW_SEL_NETWORK" $(( NW_FOCUS == 3 ? 1 : 0 )) "blue"

  # === RIGHT PANEL ===

  # Tab header
  tui_box "$TAB_ROW" "$RIGHT_COL" "$TAB_H" "$RIGHT_W" "" "white"
  local tab_str=""
  local ti
  for (( ti=0; ti<NW_TAB_COUNT; ti++ )); do
    if (( ti == NW_CURRENT_TAB )); then
      tab_str+=" [${TAB_NAMES[$ti]}] "
    else
      tab_str+="  ${TAB_NAMES[$ti]}  "
    fi
    (( ti < NW_TAB_COUNT - 1 )) && tab_str+="│"
  done
  # Render tab header text
  tui_goto $(( TAB_ROW + 1 )) $(( RIGHT_COL + 1 ))
  local ti2
  for (( ti2=0; ti2<NW_TAB_COUNT; ti2++ )); do
    if (( ti2 == NW_CURRENT_TAB )); then
      tui_print '%b%b [%s] %b' "${COLOR[bold]}" "${COLOR[cyan]}" "${TAB_NAMES[$ti2]}" "${COLOR[reset]}"
    else
      tui_print '%b  %s  %b' "${COLOR[dim]}" "${TAB_NAMES[$ti2]}" "${COLOR[reset]}"
    fi
    (( ti2 < NW_TAB_COUNT - 1 )) && tui_print '%b│%b' "${COLOR[dim]}" "${COLOR[reset]}"
  done

  # Render tab content
  render_content_tab

  # Content box
  tui_box "$CONTENT_ROW" "$RIGHT_COL" "$CONTENT_H" "$RIGHT_W" "" "cyan"

  # === HELP BAR ===
  tui_goto "$HELP_ROW" 1
  tui_print '%b%b' "${COLOR[bg_blue]}" "${COLOR[white]}"
  tui_print '%s' " q:Quit ←→:Tabs ↑↓:Nav s:Start/Stop r:Restart t:Exec d:Del m:Mark C-a:SelAll l:Logs a:AutoScr F5:Refresh"
  tui_clear_eol
  tui_print '%b' "${COLOR[reset]}"

  # === NOTIFICATION ===
  if [[ -n "$NW_NOTIFY_MSG" ]] && (( SECONDS < NW_NOTIFY_UNTIL )); then
    local msg=" $NW_NOTIFY_MSG "
    local msg_len=${#msg}
    local notify_col=$(( (TERM_COLS - msg_len) / 2 ))
    (( notify_col < 1 )) && notify_col=1
    local notify_row=$(( TERM_ROWS / 2 ))
    local nc="${COLOR[$NW_NOTIFY_COLOR]:-${COLOR[green]}}"

    tui_goto "$notify_row" "$notify_col"
    tui_print '%b%b%s%b' "$nc" "${COLOR[bold]}" "$msg" "${COLOR[reset]}"
  elif (( SECONDS >= NW_NOTIFY_UNTIL )); then
    NW_NOTIFY_MSG=""
  fi

  tui_print '%b' "${COLOR[reset]}"
  tui_end_update
  printf '%s' "${NW_RENDER_PARTS[@]:-}"
}

# ---------------------------------------------------------------------------
# Render the right-panel content based on current tab
# ---------------------------------------------------------------------------
render_content_tab() {
  _inspect_poll_async
  local inner_w=$(( RIGHT_W - 2 ))
  local inner_h=$(( CONTENT_H - 2 ))
  local start_row=$(( CONTENT_ROW + 1 ))
  local start_col=$(( RIGHT_COL + 1 ))
  (( inner_w <= 0 || inner_h <= 0 )) && return 0

  if (( ${#CONT_NAMES[@]} == 0 )); then
    local no_cont_msg="No containers available. Start Docker or create one."
    tui_text "$start_row" "$start_col" "$no_cont_msg" "yellow"
    local pad_start=1
    while (( pad_start < inner_h )); do
      tui_goto $(( start_row + pad_start )) "$start_col"
      tui_print '%-*s' "$inner_w" ""
      (( pad_start++ ))
    done
    return
  fi

  local content=""
  case "$NW_CURRENT_TAB" in
    0) # Logs
      if [[ -n "$NW_LOGS_CONTENT" ]]; then
        content="$NW_LOGS_CONTENT"
      elif [[ "$NW_LOGS_PENDING" == true ]]; then
        content="Loading logs..."
      else
        content="No logs available for this container."
      fi
      ;;
    1) # Stats
      content=$(render_stats_content)
      ;;
    2) # Env
      if (( NW_DEFER_EXPENSIVE_RENDER > 0 )); then
        content="Environment Variables: ${CONT_NAMES[$NW_SEL_CONTAINER]:-No container selected}

Loading details..."
      else
        get_cached_env_tab
        content="$_NW_INSPECT_CONTENT"
      fi
      ;;
    3) # Config
      if (( NW_DEFER_EXPENSIVE_RENDER > 0 )); then
        content="Configuration: ${CONT_NAMES[$NW_SEL_CONTAINER]:-No container selected}

Loading details..."
      else
        get_cached_config_tab
        content="$_NW_INSPECT_CONTENT"
      fi
      ;;
    4) # Top
      if (( NW_DEFER_EXPENSIVE_RENDER > 0 )); then
        content="Top Processes: ${CONT_NAMES[$NW_SEL_CONTAINER]:-No container selected}

Loading details..."
      else
        get_cached_top_tab
        content="$_NW_INSPECT_CONTENT"
      fi
      ;;
  esac

  # Display content line by line within the box. Logs are soft-wrapped so long
  # SQL/error lines remain readable instead of disappearing past the border.
  local -a content_lines=()
  if [[ -n "$content" ]]; then
    if (( NW_CURRENT_TAB == 0 )); then
      mapfile -t content_lines < <(printf '%s' "$content" | fold -w "$inner_w" 2>/dev/null)
    else
      mapfile -t content_lines <<< "$content"
    fi
  fi

  local total_lines=${#content_lines[@]}
  if (( total_lines == 1 )) && [[ -z "${content_lines[0]}" ]]; then
    total_lines=0
    content_lines=()
  fi

  local max_scroll=0
  (( total_lines > inner_h )) && max_scroll=$(( total_lines - inner_h ))

  if (( NW_CURRENT_TAB == 0 )) && $NW_LOGS_AUTO_SCROLL; then
    NW_CONTENT_SCROLL=$max_scroll
  fi
  (( NW_CONTENT_SCROLL > max_scroll )) && NW_CONTENT_SCROLL=$max_scroll
  (( NW_CONTENT_SCROLL < 0 )) && NW_CONTENT_SCROLL=0

  local line_num=0
  local scroll="$NW_CONTENT_SCROLL"

  local blank
  printf -v blank "%-${inner_w}s" ""

  while (( line_num < inner_h )); do
    local idx=$(( scroll + line_num ))
    local display_line=""
    if (( idx < total_lines )); then
      display_line="${content_lines[$idx]}"
      if (( NW_CURRENT_TAB != 1 )); then
        (( ${#display_line} > inner_w )) && display_line="${display_line:0:$inner_w}"
      fi
    fi

    tui_goto $(( start_row + line_num )) "$start_col"
    tui_print '%s' "$blank"
    tui_goto $(( start_row + line_num )) "$start_col"
    tui_print '%s' "$display_line"

    (( line_num++ ))
  done

  NW_CONTENT_LINES=$total_lines
}

# ---------------------------------------------------------------------------
# Render stats content
# ---------------------------------------------------------------------------
render_stats_content() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"

  if [[ -z "$name" ]]; then
    echo "No container selected"
    return
  fi

  local sep
  printf -v sep '%*s' 55 ''
  sep=${sep// /-}

  printf 'Stats: %s\n' "$name"
  printf '%s\n\n' "$sep"

  if [[ "$state" != "running" ]]; then
    echo "Container is not running"
    echo "Press [s] to start"
    return
  fi

  local cpu_hist="${CPU_HISTORY[$name]:-}"
  local mem_hist="${MEM_HISTORY[$name]:-}"

  render_chart "CPU:   " "$cpu_hist" "cyan" "$NW_CHART_WIDTH"
  echo ""
  render_chart "Memory:" "$mem_hist" "green" "$NW_CHART_WIDTH"
  echo ""

  # Additional stats
  local pids="${STAT_PIDS[$name]:-N/A}"
  local net_io="${STAT_NET_IO[$name]:-0B / 0B}"
  local block_io="${STAT_BLOCK_IO[$name]:-0B / 0B}"

  printf 'PIDs:     %s\n' "$pids"
  printf 'Net I/O:  %s\n' "$net_io"
  printf 'Block IO: %s\n' "$block_io"
}

# ---------------------------------------------------------------------------
# Track the previously selected container for log stream switching
# ---------------------------------------------------------------------------
_prev_sel_container=-1

# ---------------------------------------------------------------------------
# Main event loop
# ---------------------------------------------------------------------------
main_loop() {
  NW_LAST_CONTAINER_REFRESH=$SECONDS
  NW_LAST_MISC_REFRESH=$SECONDS
  _prev_sel_container=$NW_SEL_CONTAINER
  local tick=0
  local dirty=true

  while $NW_RUNNING; do
    # Skip rendering if in fullscreen mode
    if $NW_FULLSCREEN; then
      sleep 0.1
      continue
    fi

    tick=$(( tick + 1 ))
    NW_DATA_CHANGED=false

    if (( NW_DEFER_EXPENSIVE_RENDER > 0 )); then
      (( NW_DEFER_EXPENSIVE_RENDER-- ))
      (( NW_DEFER_EXPENSIVE_RENDER == 0 )) && dirty=true
    fi

    # Poll background snapshots at a light cadence. Keyboard input still checks
    # every loop, but file parsing only happens when a producer flips pointers.
    # Background producers publish snapshots; checking them at 1Hz avoids
    # repeatedly spawning file-reading subprocesses in the hot loop.
    if (( tick % 20 == 0 )); then
      fetch_containers
      fetch_images
      fetch_volumes
      fetch_networks
    fi

    # Clamp selection
    (( NW_SEL_CONTAINER >= ${#CONT_NAMES[@]} )) && NW_SEL_CONTAINER=$(( ${#CONT_NAMES[@]} - 1 ))
    (( NW_SEL_CONTAINER < 0 )) && NW_SEL_CONTAINER=0
    (( NW_SEL_IMAGE >= ${#IMG_REPOS[@]} )) && NW_SEL_IMAGE=$(( ${#IMG_REPOS[@]} - 1 ))
    (( NW_SEL_IMAGE < 0 )) && NW_SEL_IMAGE=0
    (( NW_SEL_VOLUME >= ${#VOL_NAMES[@]} )) && NW_SEL_VOLUME=$(( ${#VOL_NAMES[@]} - 1 ))
    (( NW_SEL_VOLUME < 0 )) && NW_SEL_VOLUME=0
    (( NW_SEL_NETWORK >= ${#NET_NAMES[@]} )) && NW_SEL_NETWORK=$(( ${#NET_NAMES[@]} - 1 ))
    (( NW_SEL_NETWORK < 0 )) && NW_SEL_NETWORK=0

    # Read stats data
    if (( tick % 40 == 0 )); then
      read_stats 2>/dev/null || true
    fi

    # Switch log stream if container selection changed
    local selected_container="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
    if (( NW_SEL_CONTAINER != _prev_sel_container )); then
      _prev_sel_container=$NW_SEL_CONTAINER
      NW_CONTENT_SCROLL=0
      dirty=true
    fi

    if (( NW_CURRENT_TAB == 0 )) && [[ -n "$selected_container" && "$selected_container" != "$NW_LOGS_CONTAINER" ]]; then
      start_log_stream "$selected_container" "$NW_LOGS_TAIL_DEFAULT"
      dirty=true
    fi

    # Read new streams aggressively until their first snapshot arrives, then
    # use the normal lower-cost polling cadence.
    if (( NW_CURRENT_TAB == 0 )) && { [[ "$NW_LOGS_PENDING" == true ]] || (( tick % 10 == 0 )); }; then
      read_logs 2>/dev/null || true
    fi

    if $NW_DATA_CHANGED; then
      dirty=true
    fi

    if [[ -n "$NW_NOTIFY_MSG" ]] && (( SECONDS >= NW_NOTIFY_UNTIL )); then
      NW_NOTIFY_MSG=""
      dirty=true
    fi

    # Read keyboard input. Drain a small queued batch so held navigation keys
    # do not lag behind terminal repeat.
    if read_key; then
      local keys_processed=0
      local old_input_timeout
      while true; do
        handle_key "$KEY"
        if (( NW_CURRENT_TAB >= 2 && NW_FOCUS == 0 )); then
          case "$KEY" in
            UP|DOWN|HOME|END)
              NW_DEFER_EXPENSIVE_RENDER=2
              ;;
          esac
        fi
        dirty=true
        (( keys_processed++ ))

        $NW_RUNNING || break
        (( keys_processed >= ${NW_INPUT_BATCH_MAX:-16} )) && break

        old_input_timeout="$NW_INPUT_TIMEOUT"
        NW_INPUT_TIMEOUT=0
        if ! read_key; then
          NW_INPUT_TIMEOUT="$old_input_timeout"
          break
        fi
        NW_INPUT_TIMEOUT="$old_input_timeout"
      done
    fi

    if $dirty || [[ "$NW_NEEDS_RENDER" == "true" ]]; then
      render_ui
      dirty=false
      NW_NEEDS_RENDER=false
    fi
  done
}

# ---------------------------------------------------------------------------
# Run!
# ---------------------------------------------------------------------------
main_loop
