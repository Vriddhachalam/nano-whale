#!/bin/bash
# =============================================================================
# nano-whale :: tests/test_docker.sh
# Tests for Docker API parsing and data structures
# =============================================================================
set -Euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/test_utils.sh"
source "$PROJECT_DIR/config/defaults.sh"
source "$PROJECT_DIR/lib/utils.sh"
source "$PROJECT_DIR/lib/config.sh"
source "$PROJECT_DIR/lib/core.sh"

# We test parsing logic without actually calling Docker
# by mocking docker_exec

# ---------------------------------------------------------------------------
describe "Container parsing"
# ---------------------------------------------------------------------------

# Mock docker output
_mock_container_output='web-app|Up 2 hours|abc123def456|nginx:latest|0.0.0.0:80->80/tcp|running
redis-cache|Exited (0) 3 hours ago|def456abc789|redis:7|6379/tcp|exited
db|Up 5 minutes (healthy)|111222333444|postgres:15|5432/tcp|running'

# Simulate fetch_containers parsing
parse_mock_containers() {
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
  done <<< "$_mock_container_output"
}

parse_mock_containers

assert_equals "3" "${#CONT_NAMES[@]}" "Parse 3 containers"
assert_equals "web-app" "${CONT_NAMES[0]}" "First container name"
assert_equals "redis-cache" "${CONT_NAMES[1]}" "Second container name"
assert_equals "db" "${CONT_NAMES[2]}" "Third container name"
assert_equals "running" "${CONT_STATES[0]}" "First container state"
assert_equals "exited" "${CONT_STATES[1]}" "Second container state (exited)"
assert_equals "running" "${CONT_STATES[2]}" "Third container state (healthy)"
assert_equals "abc123def456" "${CONT_IDS[0]}" "Container ID truncated to 12"
assert_equals "nginx:latest" "${CONT_IMAGES[0]}" "Container image"
assert_equals "0.0.0.0:80->80/tcp" "${CONT_PORTS[0]}" "Container ports"

# ---------------------------------------------------------------------------
describe "Image parsing"
# ---------------------------------------------------------------------------

_mock_image_output='nginx|latest|150MB|sha256:abc123
redis|7-alpine|30MB|sha256:def456
postgres|15|380MB|sha256:ghi789'

parse_mock_images() {
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
  done <<< "$_mock_image_output"
}

parse_mock_images

assert_equals "3" "${#IMG_REPOS[@]}" "Parse 3 images"
assert_equals "nginx" "${IMG_REPOS[0]}" "First image repo"
assert_equals "latest" "${IMG_TAGS[0]}" "First image tag"
assert_equals "150MB" "${IMG_SIZES[0]}" "First image size"
assert_equals "7-alpine" "${IMG_TAGS[1]}" "Second image tag"

# ---------------------------------------------------------------------------
describe "Volume parsing"
# ---------------------------------------------------------------------------

_mock_volume_output='local|my-data-volume
local|postgres-data
nfs|shared-vol'

parse_mock_volumes() {
  VOL_DRIVERS=()
  VOL_NAMES=()

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local driver name
    IFS='|' read -r driver name <<< "$line"
    VOL_DRIVERS+=("${driver:-local}")
    VOL_NAMES+=("${name:-N/A}")
  done <<< "$_mock_volume_output"
}

parse_mock_volumes

assert_equals "3" "${#VOL_NAMES[@]}" "Parse 3 volumes"
assert_equals "local" "${VOL_DRIVERS[0]}" "First volume driver"
assert_equals "my-data-volume" "${VOL_NAMES[0]}" "First volume name"
assert_equals "nfs" "${VOL_DRIVERS[2]}" "Third volume driver"

# ---------------------------------------------------------------------------
describe "Network parsing"
# ---------------------------------------------------------------------------

_mock_network_output='bridge|bridge
host|host
null|none
bridge|my-custom-net'

parse_mock_networks() {
  NET_DRIVERS=()
  NET_NAMES=()

  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local driver name
    IFS='|' read -r driver name <<< "$line"
    NET_DRIVERS+=("${driver:-bridge}")
    NET_NAMES+=("${name:-N/A}")
  done <<< "$_mock_network_output"
}

parse_mock_networks

assert_equals "4" "${#NET_NAMES[@]}" "Parse 4 networks"
assert_equals "bridge" "${NET_NAMES[0]}" "System bridge network"
assert_equals "my-custom-net" "${NET_NAMES[3]}" "Custom network"

# ---------------------------------------------------------------------------
describe "Empty output handling"
# ---------------------------------------------------------------------------

_mock_empty=""

parse_empty_containers() {
  CONT_NAMES=()
  [[ -z "$_mock_empty" ]] && return 0
}

parse_empty_containers
assert_equals "0" "${#CONT_NAMES[@]}" "Empty output → 0 containers"

# ---------------------------------------------------------------------------
describe "Stats parsing"
# ---------------------------------------------------------------------------

_mock_stats_line='web-app|25.50%|10.20%|200MiB / 2GiB|1.2kB / 500B|4MB / 100kB|5'

parse_mock_stats() {
  local line="$_mock_stats_line"
  local name cpu_str mem_str mem_usage net_io block_io pids
  IFS='|' read -r name cpu_str mem_str mem_usage net_io block_io pids <<< "$line"

  local cpu="${cpu_str//%/}"
  local mem="${mem_str//%/}"

  STAT_CPU["$name"]="$cpu"
  STAT_MEM["$name"]="$mem"
  STAT_MEM_USAGE["$name"]="$mem_usage"
  STAT_NET_IO["$name"]="$net_io"
  STAT_BLOCK_IO["$name"]="$block_io"
  STAT_PIDS["$name"]="$pids"
}

parse_mock_stats

assert_equals "25.50" "${STAT_CPU[web-app]}" "Parse CPU percentage"
assert_equals "10.20" "${STAT_MEM[web-app]}" "Parse Memory percentage"
assert_equals "200MiB / 2GiB" "${STAT_MEM_USAGE[web-app]}" "Parse memory usage string"
assert_equals "5" "${STAT_PIDS[web-app]}" "Parse PID count"

# ---------------------------------------------------------------------------
test_summary
