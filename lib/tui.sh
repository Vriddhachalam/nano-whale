#!/bin/bash
# =============================================================================
# nano-whale :: lib/tui.sh
# ANSI terminal rendering engine — boxes, lists, colors, cursor control
# =============================================================================

# ---------------------------------------------------------------------------
# Color codes
# ---------------------------------------------------------------------------
declare -A COLOR=(
  [reset]='\033[0m'
  [bold]='\033[1m'
  [dim]='\033[2m'
  [black]='\033[30m'
  [red]='\033[31m'
  [green]='\033[32m'
  [yellow]='\033[33m'
  [blue]='\033[34m'
  [magenta]='\033[35m'
  [cyan]='\033[36m'
  [white]='\033[37m'
  [bg_black]='\033[40m'
  [bg_red]='\033[41m'
  [bg_green]='\033[42m'
  [bg_yellow]='\033[43m'
  [bg_blue]='\033[44m'
  [bg_magenta]='\033[45m'
  [bg_cyan]='\033[46m'
  [bg_white]='\033[47m'
  [bg_default]='\033[49m'
  [reverse]='\033[7m'
)

# Box-drawing characters (Unicode)
BOX_TL="┌" BOX_TR="┐" BOX_BL="└" BOX_BR="┘"
BOX_H="─" BOX_V="│"

# ---------------------------------------------------------------------------
# Double buffering helper
# ---------------------------------------------------------------------------
NW_RENDER_BUFFER=""
declare -a NW_RENDER_PARTS=()

tui_print() {
  local _tmp
  printf -v _tmp "$@"
  NW_RENDER_PARTS+=("$_tmp")
}

tui_print_repeat() {
  local char="$1" count="$2" line
  (( count <= 0 )) && return 0
  printf -v line '%*s' "$count" ''
  line=${line// /$char}
  tui_print '%s' "$line"
}

# ---------------------------------------------------------------------------
# Terminal control
# ---------------------------------------------------------------------------
tui_init() {
  # Save terminal state, switch to alternate buffer, hide cursor
  printf '\033[?1049h'   # alternate screen buffer
  printf '\033[?25l'     # hide cursor
  printf '\033[2J'       # clear screen
  # Disable line wrapping
  printf '\033[?7l'
  stty -echo -icanon min 0 time 0 2>/dev/null || true
}

tui_restore() {
  printf '\033[?7h'      # re-enable line wrapping
  printf '\033[?25h'     # show cursor
  printf '\033[?1049l'   # restore main screen buffer
  stty sane 2>/dev/null || true
}

# Welcome screen
tui_welcome() { 
    printf '%bWelcome to nano-whale%b\n' "${COLOR[green]}" "${COLOR[reset]}"
    sleep 1
}

# Move cursor to row, col (1-based)
tui_goto() {
  tui_print '\033[%d;%dH' "$1" "$2"
}

# Clear from cursor to end of line
tui_clear_eol() {
  tui_print '\033[K'
}

# Clear entire screen
tui_clear() {
  if [[ "${NW_NEEDS_CLEAR:-false}" == "true" ]]; then
    tui_print '\033[2J\033[H'
    NW_NEEDS_CLEAR=false
  else
    tui_print '\033[H'
  fi
}

# Ask capable terminals to present the complete buffered frame atomically.
tui_begin_update() {
  tui_print '\033[?2026h'
}

tui_end_update() {
  NW_RENDER_PARTS+=($'\033[?2026l')
}

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

# Draw a horizontal line
# Usage: tui_hline row col width [char]
tui_hline() {
  local row=$1 col=$2 width=$3 char="${4:-$BOX_H}"
  tui_goto "$row" "$col"
  tui_print_repeat "$char" "$width"
}

# Draw a box border (just the border, no fill)
# Usage: tui_box row col height width label [border_color]
tui_box() {
  local row=$1 col=$2 height=$3 width=$4 label="$5" bcolor="${6:-white}"
  (( height < 2 || width < 2 )) && return 0

  local color_code="${COLOR[$bcolor]:-${COLOR[white]}}"
  local r="${COLOR[reset]}"

  # Top border
  tui_goto "$row" "$col"
  tui_print '%b%s' "$color_code" "$BOX_TL"
  local inner=$(( width - 2 ))
  local i
  tui_print_repeat "$BOX_H" "$inner"
  tui_print '%s%b' "$BOX_TR" "$r"

  # Label on top border
  if [[ -n "$label" ]]; then
    local lbl=" $label "
    local lbl_len=${#lbl}
    tui_goto "$row" $(( col + 1 ))
  tui_print '%b%b%s%b' "$color_code" "${COLOR[bold]}" "$lbl" "$r"
  fi

  # Side borders
  for (( i=1; i<height-1; i++ )); do
    tui_goto $(( row + i )) "$col"
  tui_print '%b%s%b' "$color_code" "$BOX_V" "$r"
    tui_goto $(( row + i )) $(( col + width - 1 ))
  tui_print '%b%s%b' "$color_code" "$BOX_V" "$r"
  done

  # Bottom border
  tui_goto $(( row + height - 1 )) "$col"
  tui_print '%b%s' "$color_code" "$BOX_BL"
  tui_print_repeat "$BOX_H" "$inner"
  tui_print '%s%b' "$BOX_BR" "$r"
}

# Fill a region with spaces (clear box interior)
# Usage: tui_fill row col height width
tui_fill() {
  local row=$1 col=$2 height=$3 width=$4
  local blank
  printf -v blank "%-${width}s" ""
  local i
  for (( i=0; i<height; i++ )); do
    tui_goto $(( row + i )) "$col"
  tui_print '%s' "$blank"
  done
}

# Write text at position with color
# Usage: tui_text row col text [color]
tui_text() {
  local row=$1 col=$2 text="$3" color="${4:-}"
  tui_goto "$row" "$col"
  if [[ -n "$color" ]]; then
  tui_print '%b%s%b' "${COLOR[$color]:-}" "$text" "${COLOR[reset]}"
  else
  tui_print '%s' "$text"
  fi
}

# Write colored+bold text
tui_text_bold() {
  local row=$1 col=$2 text="$3" color="${4:-white}"
  tui_goto "$row" "$col"
  tui_print '%b%b%s%b' "${COLOR[bold]}" "${COLOR[$color]:-}" "$text" "${COLOR[reset]}"
}

# ---------------------------------------------------------------------------
# List rendering — render a scrollable list inside a box
# Usage: tui_list row col height width items_array selected_index focus border_color [marks_array]
# ---------------------------------------------------------------------------
tui_render_list() {
  local row=$1 col=$2 height=$3 width=$4
  local -n _items=$5
  local selected=$6 has_focus=$7 bcolor="${8:-white}"
  local -n _marks=${9:-_NW_EMPTY_MARKS} 2>/dev/null || true

  local inner_h=$(( height - 2 ))
  local inner_w=$(( width - 2 ))
  (( inner_h <= 0 || inner_w <= 0 )) && return 0
  local count=${#_items[@]}

  # Calculate scroll offset to keep selected item visible
  local scroll=0
  if (( selected >= inner_h )); then
    scroll=$(( selected - inner_h + 1 ))
  fi

  local i
  for (( i=0; i<inner_h; i++ )); do
    local idx=$(( scroll + i ))
    local r=$(( row + 1 + i ))
    tui_goto "$r" $(( col + 1 ))

    if (( idx < count )); then
      local item="${_items[$idx]}"
      local display_item
      display_item="$item"
      (( ${#display_item} > inner_w )) && display_item="${display_item:0:$inner_w}"
      printf -v display_item "%-${inner_w}s" "$display_item"

      if (( idx == selected && has_focus )); then
        # Highlighted (selected + focused)
  tui_print '%b%b%s%b' "${COLOR[bg_blue]}" "${COLOR[white]}${COLOR[bold]}" "$display_item" "${COLOR[reset]}"
      elif (( idx == selected )); then
        # Selected but not focused
  tui_print '%b%b%s%b' "${COLOR[dim]}" "${COLOR[reverse]}" "$display_item" "${COLOR[reset]}"
      else
  tui_print '%s' "$display_item"
      fi
    else
      # Empty line
  tui_print "%-${inner_w}s" ""
    fi
  done
}

# ---------------------------------------------------------------------------
# Dummy empty marks array for when marks aren't passed
# ---------------------------------------------------------------------------
declare -A _NW_EMPTY_MARKS=()

# ---------------------------------------------------------------------------
# Layout calculation
# ---------------------------------------------------------------------------
calc_layout() {
  update_term_size
  (( TERM_COLS < 60 )) && TERM_COLS=60
  (( TERM_ROWS < 15 )) && TERM_ROWS=15

  HELP_ROW=$TERM_ROWS

  # Left panel width: 40% of terminal
  LEFT_W=$(( TERM_COLS * 40 / 100 ))
  (( LEFT_W < 30 )) && LEFT_W=30
  (( LEFT_W > TERM_COLS - 30 )) && LEFT_W=$(( TERM_COLS - 30 ))

  # Right panel
  RIGHT_W=$(( TERM_COLS - LEFT_W ))
  RIGHT_COL=$(( LEFT_W + 1 ))

  # Vertical distribution for left panel (rows)
  # Row 1-2:  Device box (height 3)
  # Row 3+:   Containers (~27%), Images (~23%), Volumes (~22%), Networks (~23%)
  DEVICE_ROW=1
  DEVICE_H=3

  local avail=$(( HELP_ROW - DEVICE_H - 1 ))  # -1 for help bar
  (( avail < 12 )) && avail=12

  CONT_ROW=$(( DEVICE_H + 1 ))
  CONT_H=$(( avail * 27 / 100 ))
  (( CONT_H < 5 )) && CONT_H=5

  IMG_ROW=$(( CONT_ROW + CONT_H ))
  IMG_H=$(( avail * 23 / 100 ))
  (( IMG_H < 4 )) && IMG_H=4

  VOL_ROW=$(( IMG_ROW + IMG_H ))
  VOL_H=$(( avail * 22 / 100 ))
  (( VOL_H < 4 )) && VOL_H=4

  NET_ROW=$(( VOL_ROW + VOL_H ))
  NET_H=$(( HELP_ROW - NET_ROW ))   # fill remaining above help bar
  (( NET_H < 4 )) && NET_H=4

  # Right panel
  TAB_ROW=1
  TAB_H=3
  CONTENT_ROW=4
  CONTENT_H=$(( HELP_ROW - CONTENT_ROW ))
  (( CONTENT_H < 3 )) && CONTENT_H=3
  CONTENT_INNER_H=$(( CONTENT_H - 2 ))
}

# ---------------------------------------------------------------------------
# Format data into display strings
# ---------------------------------------------------------------------------

# Format container list items
format_containers() {
  local -n _out=$1
  _out=()
  local i
  for (( i=0; i<${#CONT_NAMES[@]}; i++ )); do
    local name="${CONT_NAMES[$i]}"
    local state="${CONT_STATES[$i]}"
    local cpu="${STAT_CPU[$name]:-0}"
    local ports="${CONT_PORTS[$i]}"
    local mark=" "
    [[ -n "${MARKED_CONTAINERS[$name]:-}" ]] && mark="✓"

    local status_str
    case "$state" in
      running) status_str="● running" ;;
      exited)  status_str="○ exited " ;;
      paused)  status_str="◑ paused " ;;
      *)       status_str="? $state " ;;
    esac

    local disp_name
    disp_name="$name"
    (( ${#disp_name} > 18 )) && disp_name="${disp_name:0:18}"
    printf -v disp_name "%-18s" "$disp_name"

    local cpu_str
    if [[ "$state" == "running" ]]; then
  printf -v cpu_str "%6s%%" "$cpu"
    else
      cpu_str="      -"
    fi

    local port_str
    port_str="$ports"
    (( ${#port_str} > 12 )) && port_str="${port_str:0:12}"

    _out+=("[$mark] $status_str $disp_name $cpu_str $port_str")
  done

  if (( ${#_out[@]} == 0 )); then
    _out+=("  No containers")
  fi
}

# Fit a value to a maximum width while preserving its beginning.
_tui_fit_start() {
  local value="$1" width="$2"
  _TUI_FIT_RESULT=""
  (( width <= 0 )) && return 0
  if (( ${#value} > width )); then
    if (( width > 3 )); then
      _TUI_FIT_RESULT="${value:0:$(( width - 3 ))}..."
    else
      _TUI_FIT_RESULT="${value:0:$width}"
    fi
  else
    _TUI_FIT_RESULT="$value"
  fi
}

# Format image list items. The repository reference is always prioritized.
format_images() {
  local -n _out=$1
  local width="${2:-0}"
  _out=()
  local inner_w=$(( width - 2 ))
  local i
  for (( i=0; i<${#IMG_REPOS[@]}; i++ )); do
    local repo="${IMG_REPOS[$i]}"
    local tag="${IMG_TAGS[$i]:-latest}"
    local size="${IMG_SIZES[$i]:-0B}"
    local id="${IMG_IDS[$i]:-}"
    local mark=" "
    [[ -n "${MARKED_IMAGES[$id]:-}" ]] && mark="✓"

    local prefix="[$mark] "
    local name="$repo:$tag"
    local metadata="$size"
    [[ -n "$id" ]] && metadata+=" $id"
    local available=$(( inner_w - ${#prefix} ))
    local rendered="$name"
    if (( available > ${#name} + 1 )); then
      _tui_fit_start "$metadata" "$(( available - ${#name} - 1 ))"
      rendered+=" $_TUI_FIT_RESULT"
    fi
    _tui_fit_start "$rendered" "$available"
    _out+=("$prefix$_TUI_FIT_RESULT")
  done

  if (( ${#_out[@]} == 0 )); then
    _out+=("  No images")
  fi
}

# Format volume list items. The volume name is prioritized over its driver.
format_volumes() {
  local -n _out=$1
  local width="${2:-0}"
  _out=()
  local inner_w=$(( width - 2 ))
  local i
  for (( i=0; i<${#VOL_NAMES[@]}; i++ )); do
    local driver="${VOL_DRIVERS[$i]}"
    local name="${VOL_NAMES[$i]}"
    local mark=" "
    [[ -n "${MARKED_VOLUMES[$name]:-}" ]] && mark="✓"

    local prefix="[$mark] "
    local available=$(( inner_w - ${#prefix} ))
    local rendered="$name"
    if (( available > ${#name} + 1 )); then
      _tui_fit_start "$driver" "$(( available - ${#name} - 1 ))"
      rendered+=" $_TUI_FIT_RESULT"
    fi
    _tui_fit_start "$rendered" "$available"
    _out+=("$prefix$_TUI_FIT_RESULT")
  done

  if (( ${#_out[@]} == 0 )); then
    _out+=("  No volumes")
  fi
}

# Format network list items. Driver and system labels are optional metadata.
format_networks() {
  local -n _out=$1
  local width="${2:-0}"
  _out=()
  local inner_w=$(( width - 2 ))
  local i
  for (( i=0; i<${#NET_NAMES[@]}; i++ )); do
    local driver="${NET_DRIVERS[$i]}"
    local name="${NET_NAMES[$i]}"
    local suffix=""
    case "$name" in bridge|host|none) suffix=" (system)" ;; esac

    local prefix="    "
    local available=$(( inner_w - ${#prefix} ))
    local rendered="$name"
    local metadata="$driver$suffix"
    if (( available > ${#name} + 1 )); then
      _tui_fit_start "$metadata" "$(( available - ${#name} - 1 ))"
      rendered+=" $_TUI_FIT_RESULT"
    fi
    _tui_fit_start "$rendered" "$available"
    _out+=("$prefix$_TUI_FIT_RESULT")
  done

  if (( ${#_out[@]} == 0 )); then
    _out+=("  No networks")
  fi
}
