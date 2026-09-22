#!/bin/bash
# =============================================================================
# nano-whale :: lib/utils.sh
# Utility helpers — logging, error handling, cleanup, dependency checks
# =============================================================================

# ---------------------------------------------------------------------------
# Logging helpers (all go to stderr so they never pollute stdout)
# ---------------------------------------------------------------------------
log() {
  printf '\033[1;32m[nano-whale]\033[0m %s\n' "$*" >&2
}

warn() {
  printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2
}

die() {
  local code="${2:-1}"
  printf '\033[1;31m[ERROR]\033[0m %s\n' "$1" >&2
  exit "$code"
}

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_command() {
  local cmd="$1"
  local msg="${2:-Required command '$cmd' not found. Please install it.}"
  command_exists "$cmd" || die "$msg" 127
}

nw_has_gnu_timeout() {
  [[ -n "${_NW_HAS_GNU_TIMEOUT:-}" ]] && [[ "$_NW_HAS_GNU_TIMEOUT" == "true" ]] && return 0
  [[ -n "${_NW_HAS_GNU_TIMEOUT:-}" ]] && return 1

  if command_exists timeout && timeout --version >/dev/null 2>&1; then
    _NW_HAS_GNU_TIMEOUT=true
    return 0
  fi

  _NW_HAS_GNU_TIMEOUT=false
  return 1
}

nw_run_with_timeout() {
  local seconds="$1"
  shift

  if nw_has_gnu_timeout; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# Temporary file / directory management
# ---------------------------------------------------------------------------
declare -a _NW_TMPFILES=()

nw_mktemp() {
  local f
  f="$(mktemp "${1:---tmpdir}" "nano-whale.XXXXXXXXXX")" || die "Failed to create temp file"
  _NW_TMPFILES+=("$f")
  printf '%s' "$f"
}

# ---------------------------------------------------------------------------
# Cleanup — called by EXIT trap
# ---------------------------------------------------------------------------
_nw_cleanup() {
  if declare -F clear_inspect_caches >/dev/null 2>&1; then
    clear_inspect_caches 2>/dev/null || true
  fi

  # Kill background jobs we may have started
  if [[ -n "${_NW_STATS_PID:-}" ]] && kill -0 "$_NW_STATS_PID" 2>/dev/null; then
    kill "$_NW_STATS_PID" 2>/dev/null || true
  fi

  if [[ -n "${_NW_LOGS_PID:-}" ]] && kill -0 "$_NW_LOGS_PID" 2>/dev/null; then
    kill "$_NW_LOGS_PID" 2>/dev/null || true
  fi

  local action_pid
  for action_pid in "${_NW_ACTION_PIDS[@]:-}"; do
    if [[ -n "$action_pid" ]] && kill -0 "$action_pid" 2>/dev/null; then
      kill "$action_pid" 2>/dev/null || true
    fi
  done

  stop_data_streams 2>/dev/null || true

  # Remove temp files
  local f
  for f in "${_NW_TMPFILES[@]:-}"; do
    [[ -e "$f" ]] && rm -rf "$f" 2>/dev/null || true
  done

  # Restore terminal state
  tui_restore 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Human-readable byte sizes
# ---------------------------------------------------------------------------
human_bytes() {
  local n="$1"
  local -a units=(B kB MB GB TB)
  local i=0
  # Work with integers — multiply by 10 to get one decimal place
  local n10
  n10=$(printf '%.0f' "$(echo "$n * 10" | bc 2>/dev/null || echo "$((n * 10))")" 2>/dev/null || echo "$((n * 10))")

  while (( n10 >= 10240 && i < ${#units[@]} - 1 )); do
    n10=$(( n10 / 1024 ))
    (( i++ ))
  done

  local whole=$(( n10 / 10 ))
  local frac=$(( n10 % 10 ))
  printf '%d.%d%s' "$whole" "$frac" "${units[$i]}"
}

# ---------------------------------------------------------------------------
# Safe string truncation (for column formatting)
# ---------------------------------------------------------------------------
str_trunc() {
  local str="$1"
  local max="$2"
  if (( ${#str} > max )); then
    printf '%s' "${str:0:$max}"
  else
    printf '%s' "$str"
  fi
}

str_pad() {
  local str="$1"
  local width="$2"
  printf "%-${width}s" "$str"
}

shell_quote() {
  printf '%q' "$1"
}
