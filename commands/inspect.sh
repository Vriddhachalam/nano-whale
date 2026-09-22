#!/bin/bash
# =============================================================================
# nano-whale :: commands/inspect.sh
# Content rendering for Env, Config, and Top tabs
# =============================================================================

declare -A _NW_ENV_TAB_CACHE=()
declare -A _NW_ENV_TAB_CACHE_AT=()
declare -A _NW_CONFIG_TAB_CACHE=()
declare -A _NW_CONFIG_TAB_CACHE_AT=()
declare -A _NW_TOP_TAB_CACHE=()
declare -A _NW_TOP_TAB_CACHE_AT=()
_NW_INSPECT_CONTENT=""
_NW_INSPECT_PENDING_PID=""
_NW_INSPECT_PENDING_FILE=""
_NW_INSPECT_PENDING_KEY=""

_inspect_poll_async() {
  [[ -n "$_NW_INSPECT_PENDING_PID" ]] || return 0
  if kill -0 "$_NW_INSPECT_PENDING_PID" 2>/dev/null; then
    return 0
  fi

  wait "$_NW_INSPECT_PENDING_PID" 2>/dev/null || true
  local output=""
  [[ -f "$_NW_INSPECT_PENDING_FILE" ]] && output=$(<"$_NW_INSPECT_PENDING_FILE")
  local kind="${_NW_INSPECT_PENDING_KEY%%|*}"
  local name="${_NW_INSPECT_PENDING_KEY#*|}"
  local now=$SECONDS
  case "$kind" in
    env)
      _NW_ENV_TAB_CACHE["$name"]="$output"
      _NW_ENV_TAB_CACHE_AT["$name"]=$now
      ;;
    config)
      _NW_CONFIG_TAB_CACHE["$name"]="$output"
      _NW_CONFIG_TAB_CACHE_AT["$name"]=$now
      ;;
    top)
      local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"
      _NW_TOP_TAB_CACHE["$name|$state"]="$output"
      _NW_TOP_TAB_CACHE_AT["$name|$state"]=$now
      ;;
  esac
  NW_DATA_CHANGED=true
  NW_NEEDS_RENDER=true
  _NW_INSPECT_PENDING_PID=""
  _NW_INSPECT_PENDING_FILE=""
  _NW_INSPECT_PENDING_KEY=""
}

_inspect_start_async() {
  local kind="$1" name="$2" key="$1|$2"
  [[ -n "$name" ]] || return 0
  _inspect_poll_async
  case "$kind" in
    env) [[ -n "${_NW_ENV_TAB_CACHE_AT[$name]+x}" ]] && return 0 ;;
    config) [[ -n "${_NW_CONFIG_TAB_CACHE_AT[$name]+x}" ]] && return 0 ;;
    top)
      local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"
      [[ -n "${_NW_TOP_TAB_CACHE_AT[$name|$state]+x}" ]] && return 0
      ;;
  esac
  if [[ "$_NW_INSPECT_PENDING_KEY" == "$key" ]]; then
    return 0
  fi
  if [[ -n "$_NW_INSPECT_PENDING_PID" ]]; then
    if kill -0 "$_NW_INSPECT_PENDING_PID" 2>/dev/null; then
      kill "$_NW_INSPECT_PENDING_PID" 2>/dev/null || true
    fi
    wait "$_NW_INSPECT_PENDING_PID" 2>/dev/null || true
  fi
  _NW_INSPECT_PENDING_FILE=$(mktemp /tmp/nw-inspect.XXXXXX)
  _NW_TMPFILES+=("$_NW_INSPECT_PENDING_FILE")
  _NW_INSPECT_PENDING_KEY="$key"
  case "$kind" in
    env) (render_env_tab >"$_NW_INSPECT_PENDING_FILE" 2>/dev/null) & ;;
    config) (render_config_tab >"$_NW_INSPECT_PENDING_FILE" 2>/dev/null) & ;;
    top) (render_top_tab >"$_NW_INSPECT_PENDING_FILE" 2>/dev/null) & ;;
  esac
  _NW_INSPECT_PENDING_PID=$!
}

clear_inspect_caches() {
  _NW_ENV_TAB_CACHE=()
  _NW_ENV_TAB_CACHE_AT=()
  _NW_CONFIG_TAB_CACHE=()
  _NW_CONFIG_TAB_CACHE_AT=()
  _NW_TOP_TAB_CACHE=()
  _NW_TOP_TAB_CACHE_AT=()
  _NW_INSPECT_CONTENT=""
  if [[ -n "$_NW_INSPECT_PENDING_PID" ]]; then
    if kill -0 "$_NW_INSPECT_PENDING_PID" 2>/dev/null; then
      kill "$_NW_INSPECT_PENDING_PID" 2>/dev/null || true
    fi
    wait "$_NW_INSPECT_PENDING_PID" 2>/dev/null || true
  fi
  _NW_INSPECT_PENDING_PID=""
  _NW_INSPECT_PENDING_FILE=""
  _NW_INSPECT_PENDING_KEY=""
}

get_cached_env_tab() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local now=$SECONDS
  local ttl=30

  if [[ -n "$name" && -n "${_NW_ENV_TAB_CACHE_AT[$name]+x}" ]] && (( now - ${_NW_ENV_TAB_CACHE_AT[$name]} < ttl )); then
    _NW_INSPECT_CONTENT="${_NW_ENV_TAB_CACHE[$name]}"
    return
  fi

  _inspect_start_async env "$name"
  _NW_INSPECT_CONTENT="Environment details are loading..."
}

get_cached_config_tab() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local now=$SECONDS
  local ttl=30

  if [[ -n "$name" && -n "${_NW_CONFIG_TAB_CACHE_AT[$name]+x}" ]] && (( now - ${_NW_CONFIG_TAB_CACHE_AT[$name]} < ttl )); then
    _NW_INSPECT_CONTENT="${_NW_CONFIG_TAB_CACHE[$name]}"
    return
  fi

  _inspect_start_async config "$name"
  _NW_INSPECT_CONTENT="Configuration details are loading..."
}

get_cached_top_tab() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"
  local key="${name}|${state}"
  local now=$SECONDS
  local ttl=2

  if [[ -n "$name" && -n "${_NW_TOP_TAB_CACHE_AT[$key]+x}" ]] && (( now - ${_NW_TOP_TAB_CACHE_AT[$key]} < ttl )); then
    _NW_INSPECT_CONTENT="${_NW_TOP_TAB_CACHE[$key]}"
    return
  fi

  _inspect_start_async top "$name"
  _NW_INSPECT_CONTENT="Process details are loading..."
}

# ---------------------------------------------------------------------------
# Render Environment Variables tab
# ---------------------------------------------------------------------------
render_env_tab() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  if [[ -z "$name" ]]; then
    echo "No container selected"
    return
  fi

  printf 'Environment Variables: %s\n' "$name"
  printf '%s\n\n' "$(printf '─%.0s' {1..55})"

  local env_output
  env_output=$(get_container_env "$name" 2>/dev/null)

  if [[ -z "$env_output" ]]; then
    echo "No environment variables found"
    return
  fi

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local key="${line%%=*}"
    local val="${line#*=}"
    if [[ "$key" != "$line" ]]; then
      printf '%s=%s\n' "$key" "$val"
    else
      printf '%s\n' "$line"
    fi
  done <<< "$env_output"
}

# ---------------------------------------------------------------------------
# Render Config / Inspect tab
# ---------------------------------------------------------------------------
render_config_tab() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  if [[ -z "$name" ]]; then
    echo "No container selected"
    return
  fi

  printf 'Configuration: %s\n' "$name"
  printf '%s\n\n' "$(printf '─%.0s' {1..55})"

  local inspect_json
  inspect_json=$(get_container_inspect "$name" 2>/dev/null)

  if [[ -z "$inspect_json" ]]; then
    echo "Failed to get container configuration"
    return
  fi

  # Check if jq is available for JSON parsing
  if command_exists jq; then
    local id created image entrypoint cmd workdir
    id=$(echo "$inspect_json" | jq -r '.[0].Id // "N/A"' 2>/dev/null | head -c 12)
    created=$(echo "$inspect_json" | jq -r '.[0].Created // "N/A"' 2>/dev/null)
    image=$(echo "$inspect_json" | jq -r '.[0].Config.Image // "N/A"' 2>/dev/null)
    entrypoint=$(echo "$inspect_json" | jq -r '.[0].Config.Entrypoint // ["N/A"] | join(" ")' 2>/dev/null)
    cmd=$(echo "$inspect_json" | jq -r '.[0].Config.Cmd // ["N/A"] | join(" ")' 2>/dev/null)
    workdir=$(echo "$inspect_json" | jq -r '.[0].Config.WorkingDir // "/"' 2>/dev/null)

    printf 'ID:         %s\n' "$id"
    printf 'Created:    %s\n' "$created"
    printf 'Image:      %s\n' "$image"
    printf 'Entrypoint: %s\n' "$entrypoint"
    printf 'Cmd:        %s\n' "$cmd"
    printf 'WorkingDir: %s\n\n' "$workdir"

    # Network Settings
    printf 'Network Settings:\n'
    local networks
    networks=$(echo "$inspect_json" | jq -r '.[0].NetworkSettings.Networks // {} | keys[]' 2>/dev/null)
    if [[ -n "$networks" ]]; then
      local net
      while IFS= read -r net; do
        local ip gw mac
        ip=$(echo "$inspect_json" | jq -r ".[0].NetworkSettings.Networks[\"$net\"].IPAddress // \"N/A\"" 2>/dev/null)
        gw=$(echo "$inspect_json" | jq -r ".[0].NetworkSettings.Networks[\"$net\"].Gateway // \"N/A\"" 2>/dev/null)
        mac=$(echo "$inspect_json" | jq -r ".[0].NetworkSettings.Networks[\"$net\"].MacAddress // \"N/A\"" 2>/dev/null)
        printf '  %s:\n' "$net"
        printf '    IP:      %s\n' "$ip"
        printf '    Gateway: %s\n' "$gw"
        printf '    MAC:     %s\n' "$mac"
      done <<< "$networks"
    else
      printf '  No networks\n'
    fi
    printf '\n'

    # Port Bindings
    printf 'Port Bindings:\n'
    local port_keys
    port_keys=$(echo "$inspect_json" | jq -r '.[0].NetworkSettings.Ports // {} | keys[]' 2>/dev/null)
    if [[ -n "$port_keys" ]]; then
      local port
      while IFS= read -r port; do
        local bindings
        bindings=$(echo "$inspect_json" | jq -r ".[0].NetworkSettings.Ports[\"$port\"] // [] | .[] | \"\(.HostIp // \"0.0.0.0\"):\(.HostPort)\"" 2>/dev/null)
        if [[ -n "$bindings" ]]; then
          local binding
          while IFS= read -r binding; do
            printf '  %s -> %s\n' "$binding" "$port"
          done <<< "$bindings"
        else
          printf '  %s (not bound)\n' "$port"
        fi
      done <<< "$port_keys"
    else
      printf '  No ports exposed\n'
    fi
    printf '\n'

    # Mounts
    printf 'Mounts:\n'
    local mount_count
    mount_count=$(echo "$inspect_json" | jq '.[0].Mounts // [] | length' 2>/dev/null)
    if (( mount_count > 0 )); then
      local idx
      for (( idx=0; idx<mount_count; idx++ )); do
        local mtype msrc mdst
        mtype=$(echo "$inspect_json" | jq -r ".[0].Mounts[$idx].Type // \"N/A\"" 2>/dev/null)
        msrc=$(echo "$inspect_json" | jq -r ".[0].Mounts[$idx].Source // \"N/A\"" 2>/dev/null)
        mdst=$(echo "$inspect_json" | jq -r ".[0].Mounts[$idx].Destination // \"N/A\"" 2>/dev/null)
        printf '  %s: %s\n' "$mtype" "$msrc"
        printf '    -> %s\n' "$mdst"
      done
    else
      printf '  No mounts\n'
    fi
    printf '\n'

    # Resource Limits
    printf 'Resource Limits:\n'
    local cpu_shares mem_limit restart_policy
    cpu_shares=$(echo "$inspect_json" | jq -r '.[0].HostConfig.CpuShares // 0' 2>/dev/null)
    mem_limit=$(echo "$inspect_json" | jq -r '.[0].HostConfig.Memory // 0' 2>/dev/null)
    restart_policy=$(echo "$inspect_json" | jq -r '.[0].HostConfig.RestartPolicy.Name // "no"' 2>/dev/null)

    printf '  CPU Shares:     %s\n' "${cpu_shares:-default}"
    if [[ "$mem_limit" != "0" && -n "$mem_limit" ]]; then
      local mem_mb=$(( mem_limit / 1024 / 1024 ))
      printf '  Memory Limit:   %sMB\n' "$mem_mb"
    else
      printf '  Memory Limit:   unlimited\n'
    fi
    printf '  Restart Policy: %s\n' "$restart_policy"
  else
    # Fallback: raw JSON output
    echo "(Install jq for formatted output)"
    echo ""
    echo "$inspect_json" | head -100
  fi
}

# ---------------------------------------------------------------------------
# Render Top Processes tab
# ---------------------------------------------------------------------------
render_top_tab() {
  local name="${CONT_NAMES[$NW_SEL_CONTAINER]:-}"
  local state="${CONT_STATES[$NW_SEL_CONTAINER]:-}"

  if [[ -z "$name" ]]; then
    echo "No container selected"
    return
  fi

  printf 'Top Processes: %s\n' "$name"
  printf '%s\n\n' "$(printf '─%.0s' {1..55})"

  if [[ "$state" != "running" ]]; then
    echo "Container is not running"
    return
  fi

  local top_output
  top_output=$(get_container_top "$name" 2>/dev/null)
  printf '%s\n' "$top_output"
}
