#!/bin/bash
# =============================================================================
# nano-whale :: tests/test_tui.sh
# Tests for TUI utility functions
# =============================================================================
set -Euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/test_utils.sh"
source "$PROJECT_DIR/config/defaults.sh"
source "$PROJECT_DIR/lib/utils.sh"
source "$PROJECT_DIR/lib/config.sh"
source "$PROJECT_DIR/lib/core.sh"

# We can't test actual ANSI rendering, but we can test layout calculation
# and formatting functions

# ---------------------------------------------------------------------------
describe "String utilities"
# ---------------------------------------------------------------------------

assert_equals "hello" "$(str_trunc 'hello world' 5)" "str_trunc truncates"
assert_equals "hello" "$(str_trunc 'hello' 10)" "str_trunc no-op when shorter"
assert_equals "hello     " "$(str_pad 'hello' 10)" "str_pad pads with spaces"
assert_equals "hello" "$(str_pad 'hello' 5)" "str_pad exact width"

# ---------------------------------------------------------------------------
describe "Platform detection"
# ---------------------------------------------------------------------------

# We can test that it runs without error
detect_platform
assert_not_empty "$NW_PLATFORM" "Platform is detected"

# ---------------------------------------------------------------------------
describe "Core state initialization"
# ---------------------------------------------------------------------------

assert_equals "0" "$NW_CURRENT_TAB" "Initial tab is 0"
assert_equals "0" "$NW_SEL_CONTAINER" "Initial container selection is 0"
assert_equals "0" "$NW_FOCUS" "Initial focus is 0 (containers)"
assert_equals "5" "${#TAB_NAMES[@]}" "5 tab names defined"
assert_equals "Logs" "${TAB_NAMES[0]}" "First tab is Logs"
assert_equals "Stats" "${TAB_NAMES[1]}" "Second tab is Stats"
assert_equals "Top" "${TAB_NAMES[4]}" "Fifth tab is Top"

# ---------------------------------------------------------------------------
describe "Marks (multi-select)"
# ---------------------------------------------------------------------------

MARKED_CONTAINERS=()
MARKED_CONTAINERS["web-app"]=1
MARKED_CONTAINERS["redis"]=1

assert_equals "2" "${#MARKED_CONTAINERS[@]}" "2 containers marked"
assert_not_empty "${MARKED_CONTAINERS[web-app]:-}" "web-app is marked"
assert_not_empty "${MARKED_CONTAINERS[redis]:-}" "redis is marked"

# Unmark
unset 'MARKED_CONTAINERS[web-app]'
assert_equals "1" "${#MARKED_CONTAINERS[@]}" "1 container after unmark"
assert_empty "${MARKED_CONTAINERS[web-app]:-}" "web-app is unmarked"

# Clear all
MARKED_CONTAINERS=()
assert_equals "0" "${#MARKED_CONTAINERS[@]}" "All marks cleared"

# ---------------------------------------------------------------------------
describe "Notification"
# ---------------------------------------------------------------------------

set_notify() {
  NW_NOTIFY_MSG="$1"
  NW_NOTIFY_COLOR="$2"
  NW_NOTIFY_UNTIL=$(( SECONDS + 3 ))
}

set_notify "Test message" "green"
assert_equals "Test message" "$NW_NOTIFY_MSG" "Notification message set"
assert_equals "green" "$NW_NOTIFY_COLOR" "Notification color set"
assert_true "(( NW_NOTIFY_UNTIL > SECONDS ))" "Notification expiry in future"

# ---------------------------------------------------------------------------
describe "Version"
# ---------------------------------------------------------------------------

assert_equals "2.0.0" "$NW_VERSION" "Version is set"

# ---------------------------------------------------------------------------
test_summary
