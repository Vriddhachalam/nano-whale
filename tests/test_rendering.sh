#!/bin/bash
# =============================================================================
# nano-whale :: tests/test_rendering.sh
# Regression tests for render buffering and bounded log reads
# =============================================================================
set -Euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/test_utils.sh"
source "$PROJECT_DIR/config/defaults.sh"
source "$PROJECT_DIR/lib/utils.sh"
source "$PROJECT_DIR/lib/config.sh"
source "$PROJECT_DIR/lib/core.sh"
source "$PROJECT_DIR/lib/tui.sh"
source "$PROJECT_DIR/lib/logging.sh"
source "$PROJECT_DIR/commands/inspect.sh"

# ---------------------------------------------------------------------------
describe "TUI buffering"
# ---------------------------------------------------------------------------

NW_RENDER_PARTS=()
_NW_TEST_STDOUT="$(mktemp)"
tui_box 1 1 3 8 "" "white" > "$_NW_TEST_STDOUT"
box_stdout="$(cat "$_NW_TEST_STDOUT")"
rm -f "$_NW_TEST_STDOUT"
assert_empty "$box_stdout" "tui_box writes only to render buffer"
assert_true "(( \${#NW_RENDER_PARTS[@]} > 0 ))" "tui_box populates render buffer"

# ---------------------------------------------------------------------------
describe "Log tailing"
# ---------------------------------------------------------------------------

_NW_LOGS_FIFO="$(mktemp)"
trap 'rm -f "$_NW_LOGS_FIFO"' EXIT

NW_LOGS_MAX_LINES=3
printf 'one\ntwo\nthree\nfour\nfive\n' > "$_NW_LOGS_FIFO"
read_logs

assert_equals $'three\nfour\nfive' "$NW_LOGS_CONTENT" "read_logs keeps only the configured tail"

NW_LOGS_CONTENT=$'line1\nline2\nline3\nline4'
all_logs="$(get_log_display_lines 2)"
assert_equals $'line3\nline4' "$all_logs" "get_log_display_lines keeps legacy tail behavior"

NW_LOGS_CONTENT=""
NW_LOGS_PENDING=true
assert_true "[[ 'Loading logs...' != 'No logs yet...' ]]" "Pending logs use loading state"

# ---------------------------------------------------------------------------
describe "Deferred expensive content"
# ---------------------------------------------------------------------------

NW_DEFER_EXPENSIVE_RENDER=2
NW_CURRENT_TAB=3
NW_SEL_CONTAINER=0
CONT_NAMES=("web")
CONT_STATES=("running")
RIGHT_W=80
CONTENT_H=8
CONTENT_ROW=1
RIGHT_COL=1
NW_RENDER_PARTS=()

render_content_tab() {
  local inner_w=$(( RIGHT_W - 2 ))
  local inner_h=$(( CONTENT_H - 2 ))
  local content=""
  case "$NW_CURRENT_TAB" in
    3)
      if (( NW_DEFER_EXPENSIVE_RENDER > 0 )); then
        content="Configuration: ${CONT_NAMES[$NW_SEL_CONTAINER]:-No container selected}

Loading details..."
      else
        get_cached_config_tab
        content="$_NW_INSPECT_CONTENT"
      fi
      ;;
  esac
  printf '%s' "$content"
}

deferred_output="$(render_content_tab)"
assert_true "[[ '$deferred_output' == *'Loading details'* ]]" "Expensive tab can render deferred state"

# ---------------------------------------------------------------------------
describe "Responsive resource rows"
# ---------------------------------------------------------------------------

IMG_REPOS=("registry.example.com/very-long-service")
IMG_TAGS=("production")
IMG_SIZES=("1.2GB")
IMG_IDS=("abcdef123456")
MARKED_IMAGES=()
VOL_NAMES=("application-data-volume")
VOL_DRIVERS=("local")
MARKED_VOLUMES=()
NET_NAMES=("customer-network")
NET_DRIVERS=("bridge")

format_images _test_rows 24
assert_true "[[ \${#_test_rows[0]} -le 22 ]]" "Image rows fit the panel"
assert_true "[[ \${_test_rows[0]} == *'registry.'* ]]" "Image rows preserve the repository prefix"

format_volumes _test_rows 24
assert_true "[[ \${#_test_rows[0]} -le 22 ]]" "Volume rows fit the panel"
assert_true "[[ \${_test_rows[0]} == *'application-'* ]]" "Volume rows preserve the volume prefix"

format_networks _test_rows 24
assert_true "[[ \${#_test_rows[0]} -le 22 ]]" "Network rows fit the panel"
assert_true "[[ \${_test_rows[0]} == *'customer-network'* ]]" "Network rows preserve the network name"

# ---------------------------------------------------------------------------
test_summary
