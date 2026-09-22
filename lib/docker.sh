#!/bin/bash
# =============================================================================
# nano-whale :: lib/docker.sh
# Docker API layer — list containers, images, volumes, networks
# =============================================================================

# ---------------------------------------------------------------------------
# Generic docker exec wrapper
# ---------------------------------------------------------------------------
docker_exec() {
  local timeout="${2:-5}"
  local output

  if output=$(nw_run_with_timeout "$timeout" "$DOCKER_CMD" $1 2>/dev/null); then
    printf '%s' "$output"
    return 0
  fi
  return 1
}

docker_exec_args() {
  local timeout="$1"
  shift
  local output

  if output=$(nw_run_with_timeout "$timeout" "$DOCKER_CMD" "$@" 2>/dev/null); then
    printf '%s' "$output"
    return 0
  fi
  return 1
}

# ---------------------------------------------------------------------------
# Background Polling Streams
# ---------------------------------------------------------------------------
start_data_streams() {
  stop_data_streams

  _NW_CONT_FIFO=$(mktemp /tmp/nw-cont.XXXXXX)
  _NW_IMG_FIFO=$(mktemp /tmp/nw-img.XXXXXX)
  _NW_VOL_FIFO=$(mktemp /tmp/nw-vol.XXXXXX)
  _NW_NET_FIFO=$(mktemp /tmp/nw-net.XXXXXX)

  _NW_TMPFILES+=("$_NW_CONT_FIFO" "${_NW_CONT_FIFO}.1" "${_NW_CONT_FIFO}.2" "${_NW_CONT_FIFO}.ptr")
  _NW_TMPFILES+=("$_NW_IMG_FIFO" "${_NW_IMG_FIFO}.1" "${_NW_IMG_FIFO}.2" "${_NW_IMG_FIFO}.ptr")
  _NW_TMPFILES+=("$_NW_VOL_FIFO" "${_NW_VOL_FIFO}.1" "${_NW_VOL_FIFO}.2" "${_NW_VOL_FIFO}.ptr")
  _NW_TMPFILES+=("$_NW_NET_FIFO" "${_NW_NET_FIFO}.1" "${_NW_NET_FIFO}.2" "${_NW_NET_FIFO}.ptr")

  (
    while true; do
      c_out=""
      next_file="${_NW_CONT_FIFO}.1"
      [[ -f "${_NW_CONT_FIFO}.ptr" ]] && [[ "$(cat "${_NW_CONT_FIFO}.ptr" 2>/dev/null)" == "$next_file" ]] && next_file="${_NW_CONT_FIFO}.2"
      
      if c_out=$($DOCKER_CMD ps -a --format '{{.Names}}|{{.Status}}|{{.ID}}|{{.Image}}|{{.Ports}}|{{.State}}' 2>/dev/null); then
        printf '%s\n' "$c_out" > "$next_file"
        printf '%s' "$next_file" > "${_NW_CONT_FIFO}.ptr"
      fi
      sleep "${NW_CONTAINER_INTERVAL:-2}"
    done
  ) &
  _NW_CONT_PID=$!

  (
    while true; do
      i_out=""
      v_out=""
      n_out=""
      i_next="${_NW_IMG_FIFO}.1"
      [[ -f "${_NW_IMG_FIFO}.ptr" ]] && [[ "$(cat "${_NW_IMG_FIFO}.ptr" 2>/dev/null)" == "$i_next" ]] && i_next="${_NW_IMG_FIFO}.2"
      v_next="${_NW_VOL_FIFO}.1"
      [[ -f "${_NW_VOL_FIFO}.ptr" ]] && [[ "$(cat "${_NW_VOL_FIFO}.ptr" 2>/dev/null)" == "$v_next" ]] && v_next="${_NW_VOL_FIFO}.2"
      n_next="${_NW_NET_FIFO}.1"
      [[ -f "${_NW_NET_FIFO}.ptr" ]] && [[ "$(cat "${_NW_NET_FIFO}.ptr" 2>/dev/null)" == "$n_next" ]] && n_next="${_NW_NET_FIFO}.2"

      if i_out=$($DOCKER_CMD images --format '{{.Repository}}|{{.Tag}}|{{.Size}}|{{.ID}}' 2>/dev/null); then
        printf '%s\n' "$i_out" > "$i_next"
        printf '%s' "$i_next" > "${_NW_IMG_FIFO}.ptr"
      fi
      if v_out=$($DOCKER_CMD volume ls --format '{{.Driver}}|{{.Name}}' 2>/dev/null); then
        printf '%s\n' "$v_out" > "$v_next"
        printf '%s' "$v_next" > "${_NW_VOL_FIFO}.ptr"
      fi
      if n_out=$($DOCKER_CMD network ls --format '{{.Driver}}|{{.Name}}' 2>/dev/null); then
        printf '%s\n' "$n_out" > "$n_next"
        printf '%s' "$n_next" > "${_NW_NET_FIFO}.ptr"
      fi
      sleep "${NW_MISC_INTERVAL:-5}"
    done
  ) &
  _NW_MISC_PID=$!
}

stop_data_streams() {
  if [[ -n "${_NW_CONT_PID:-}" ]] && kill -0 "$_NW_CONT_PID" 2>/dev/null; then
    kill "$_NW_CONT_PID" 2>/dev/null || true
  fi
  if [[ -n "${_NW_MISC_PID:-}" ]] && kill -0 "$_NW_MISC_PID" 2>/dev/null; then
    kill "$_NW_MISC_PID" 2>/dev/null || true
  fi
  _NW_CONT_PID=""
  _NW_MISC_PID=""
}

_NW_CONT_LAST_FILE=""
_NW_IMG_LAST_FILE=""
_NW_VOL_LAST_FILE=""
_NW_NET_LAST_FILE=""
_NW_SNAPSHOT_SENTINEL=$'\037__nano_whale_unset__'
_NW_CONT_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
_NW_IMG_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
_NW_VOL_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
_NW_NET_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"

# ---------------------------------------------------------------------------
# List containers → populates CONT_* arrays
# ---------------------------------------------------------------------------
fetch_containers() {
  [[ -z "${_NW_CONT_FIFO:-}" ]] || [[ ! -f "${_NW_CONT_FIFO}.ptr" ]] && return 0
  local current_file
  current_file=$(cat "${_NW_CONT_FIFO}.ptr" 2>/dev/null)
  [[ -z "$current_file" ]] || [[ ! -f "$current_file" ]] && return 0
  [[ "$current_file" == "$_NW_CONT_LAST_FILE" ]] && return 0
  _NW_CONT_LAST_FILE="$current_file"

  local content
  content=$(<"$current_file")
  [[ "$content" == "$_NW_CONT_LAST_CONTENT" ]] && return 0
  _NW_CONT_LAST_CONTENT="$content"
  NW_DATA_CHANGED=true

  CONT_NAMES=()
  CONT_STATUS=()
  CONT_IDS=()
  CONT_IMAGES=()
  CONT_PORTS=()
  CONT_STATES=()

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local name status id image ports state
    IFS='|' read -r name status id image ports state <<< "$line"
    CONT_NAMES+=("${name:-N/A}")
    CONT_STATUS+=("${status:-unknown}")
    CONT_IDS+=("${id:0:12}")
    CONT_IMAGES+=("${image:-N/A}")
    CONT_PORTS+=("${ports:-}")
    CONT_STATES+=("${state:-unknown}")
  done <<< "$content"
}

# ---------------------------------------------------------------------------
# List images → populates IMG_* arrays
# ---------------------------------------------------------------------------
fetch_images() {
  [[ -z "${_NW_IMG_FIFO:-}" ]] || [[ ! -f "${_NW_IMG_FIFO}.ptr" ]] && return 0
  local current_file
  current_file=$(cat "${_NW_IMG_FIFO}.ptr" 2>/dev/null)
  [[ -z "$current_file" ]] || [[ ! -f "$current_file" ]] && return 0
  [[ "$current_file" == "$_NW_IMG_LAST_FILE" ]] && return 0
  _NW_IMG_LAST_FILE="$current_file"

  local content
  content=$(<"$current_file")
  [[ "$content" == "$_NW_IMG_LAST_CONTENT" ]] && return 0
  _NW_IMG_LAST_CONTENT="$content"
  NW_DATA_CHANGED=true

  IMG_REPOS=()
  IMG_TAGS=()
  IMG_SIZES=()
  IMG_IDS=()

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local repo tag size id
    IFS='|' read -r repo tag size id <<< "$line"
    IMG_REPOS+=("${repo:-N/A}")
    IMG_TAGS+=("${tag:-latest}")
    IMG_SIZES+=("${size:-0B}")
    IMG_IDS+=("${id:0:12}")
  done <<< "$content"
}

# ---------------------------------------------------------------------------
# List volumes → populates VOL_* arrays
# ---------------------------------------------------------------------------
fetch_volumes() {
  [[ -z "${_NW_VOL_FIFO:-}" ]] || [[ ! -f "${_NW_VOL_FIFO}.ptr" ]] && return 0
  local current_file
  current_file=$(cat "${_NW_VOL_FIFO}.ptr" 2>/dev/null)
  [[ -z "$current_file" ]] || [[ ! -f "$current_file" ]] && return 0
  [[ "$current_file" == "$_NW_VOL_LAST_FILE" ]] && return 0
  _NW_VOL_LAST_FILE="$current_file"

  local content
  content=$(<"$current_file")
  [[ "$content" == "$_NW_VOL_LAST_CONTENT" ]] && return 0
  _NW_VOL_LAST_CONTENT="$content"
  NW_DATA_CHANGED=true

  VOL_DRIVERS=()
  VOL_NAMES=()

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local driver name
    IFS='|' read -r driver name <<< "$line"
    VOL_DRIVERS+=("${driver:-local}")
    VOL_NAMES+=("${name:-N/A}")
  done <<< "$content"
}

# ---------------------------------------------------------------------------
# List networks → populates NET_* arrays
# ---------------------------------------------------------------------------
fetch_networks() {
  [[ -z "${_NW_NET_FIFO:-}" ]] || [[ ! -f "${_NW_NET_FIFO}.ptr" ]] && return 0
  local current_file
  current_file=$(cat "${_NW_NET_FIFO}.ptr" 2>/dev/null)
  [[ -z "$current_file" ]] || [[ ! -f "$current_file" ]] && return 0
  [[ "$current_file" == "$_NW_NET_LAST_FILE" ]] && return 0
  _NW_NET_LAST_FILE="$current_file"

  local content
  content=$(<"$current_file")
  [[ "$content" == "$_NW_NET_LAST_CONTENT" ]] && return 0
  _NW_NET_LAST_CONTENT="$content"
  NW_DATA_CHANGED=true

  NET_DRIVERS=()
  NET_NAMES=()

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local driver name
    IFS='|' read -r driver name <<< "$line"
    NET_DRIVERS+=("${driver:-bridge}")
    NET_NAMES+=("${name:-N/A}")
  done <<< "$content"
}

# ---------------------------------------------------------------------------
# Get container environment variables
# ---------------------------------------------------------------------------
get_container_env() {
  local name="$1"
  docker_exec_args 5 inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$name"
}

# ---------------------------------------------------------------------------
# Get container top (processes)
# ---------------------------------------------------------------------------
get_container_top() {
  local name="$1"
  docker_exec_args 5 top "$name" || echo "Container not running"
}

# ---------------------------------------------------------------------------
# Get container inspect (JSON)
# ---------------------------------------------------------------------------
get_container_inspect() {
  local name="$1"
  docker_exec_args 10 inspect "$name"
}

# ---------------------------------------------------------------------------
# Fetch all resources
# ---------------------------------------------------------------------------
fetch_all() {
  fetch_containers
  fetch_images
  fetch_volumes
  fetch_networks
}
