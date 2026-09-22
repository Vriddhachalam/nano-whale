#!/bin/bash
# =============================================================================
# nano-whale :: lib/charts.sh
# Block-character sparkline charts for CPU/Memory visualization
# =============================================================================

# Unicode block elements for vertical bar chart (8 levels)
readonly CHART_BLOCKS=("▁" "▂" "▃" "▄" "▅" "▆" "▇" "█")

# ---------------------------------------------------------------------------
# Render a sparkline chart into content lines
# Usage: render_chart "label" history_string color max_width
#   history_string is space-separated floats
# Returns lines via stdout
# ---------------------------------------------------------------------------
render_chart() {
  local label="$1"
  local history="$2"
  local color="${3:-cyan}"
  local max_width="${4:-50}"

  local color_code="${COLOR[$color]:-${COLOR[cyan]}}"
  local r="${COLOR[reset]}"
  local bold="${COLOR[bold]}"

  # Convert history to array
  local -a data
  IFS=' ' read -ra data <<< "$history"

  local count=${#data[@]}
  if (( count < 2 )); then
    printf '%b%s%b %s 0.00%% (waiting...)' "$color_code$bold" "$label" "$r" ""
    return
  fi

  # Take last max_width values
  local start=0
  if (( count > max_width )); then
    start=$(( count - max_width ))
  fi

  local -a slice=("${data[@]:$start}")
  local n=${#slice[@]}

  # Helper to round float strings in pure bash
  local _tui_round_v
  _tui_round() {
    local v="$1"
    _tui_round_v="${v%%.*}"
    [[ -z "$_tui_round_v" ]] && _tui_round_v=0
    local frac="${v#*.}"
    if [[ "$frac" != "$v" && -n "$frac" ]]; then
      local tenth="${frac:0:1}"
      [[ "$tenth" > "4" ]] && (( _tui_round_v++ ))
    fi
  }

  # Find min/max
  local max=0 min=100
  local v
  for v in "${slice[@]}"; do
    _tui_round "$v"
    local int_v="$_tui_round_v"
    (( int_v > max )) && max=$int_v
    (( int_v < min )) && min=$int_v
  done

  local range=$(( max - min ))
  (( range == 0 )) && range=1

  # Build sparkline string
  local spark=""
  for v in "${slice[@]}"; do
    _tui_round "$v"
    local int_v="$_tui_round_v"
    local level=$(( (int_v - min) * 7 / range ))
    (( level < 0 )) && level=0
    (( level > 7 )) && level=7
    spark+="${CHART_BLOCKS[$level]}"
  done

  # Current value
  local current="${slice[$(( n - 1 ))]}"

  # Output
  printf '%b%s%b %b%s%b  %s%%  (%ds)\n' \
    "$bold" "$label" "$r" \
    "$color_code" "$spark" "$r" \
    "$current" "$(( n * 2 ))"

  # Scale labels
  printf '       %b%.0f%%%b .. %b%.0f%%%b\n' \
    "${COLOR[dim]}" "$min" "$r" \
    "${COLOR[dim]}" "$max" "$r"
}

# ---------------------------------------------------------------------------
# Add a value to a history string (space-separated, capped at MAX_HISTORY)
# Usage: history_push history_var_name value
# ---------------------------------------------------------------------------
history_push() {
  local -n _hist=$1
  local val="$2"

  if [[ -z "$_hist" ]]; then
    _hist="$val"
  else
    _hist="$_hist $val"
    # Count entries and trim if needed
    local -a parts
    IFS=' ' read -ra parts <<< "$_hist"
    if (( ${#parts[@]} > MAX_HISTORY )); then
      parts=("${parts[@]:1}")
      _hist="${parts[*]}"
    fi
  fi
}
