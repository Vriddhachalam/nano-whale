#!/bin/bash
# =============================================================================
# nano-whale :: tests/test_charts.sh
# Tests for chart rendering and history management
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
source "$PROJECT_DIR/lib/charts.sh"

# ---------------------------------------------------------------------------
describe "History push"
# ---------------------------------------------------------------------------

# Test basic history push
test_hist=""
history_push test_hist "10"
assert_equals "10" "$test_hist" "First history value"

history_push test_hist "20"
assert_equals "10 20" "$test_hist" "Two history values"

history_push test_hist "30"
assert_equals "10 20 30" "$test_hist" "Three history values"

# Test MAX_HISTORY trimming
MAX_HISTORY=5
test_hist2=""
for i in 1 2 3 4 5 6 7; do
  history_push test_hist2 "$i"
done

declare -a parts
IFS=' ' read -ra parts <<< "$test_hist2"
assert_equals "5" "${#parts[@]}" "History trimmed to MAX_HISTORY"
assert_equals "3" "${parts[0]}" "Oldest value after trim"
assert_equals "7" "${parts[4]}" "Newest value after trim"

# Reset MAX_HISTORY
MAX_HISTORY=40

# ---------------------------------------------------------------------------
describe "Chart rendering"
# ---------------------------------------------------------------------------

# With data
chart_output=$(render_chart "CPU:" "10 20 30 40 50" "cyan" 20)
assert_not_empty "$chart_output" "Chart renders with data"

# With insufficient data
chart_output2=$(render_chart "CPU:" "10" "cyan" 20)
assert_not_empty "$chart_output2" "Chart renders with single value (waiting)"

# With empty data
chart_output3=$(render_chart "CPU:" "" "cyan" 20)
assert_not_empty "$chart_output3" "Chart renders with empty data"

# ---------------------------------------------------------------------------
describe "Chart block characters"
# ---------------------------------------------------------------------------

assert_equals "8" "${#CHART_BLOCKS[@]}" "8 block character levels"
assert_equals "▁" "${CHART_BLOCKS[0]}" "Lowest block"
assert_equals "█" "${CHART_BLOCKS[7]}" "Highest block"

# ---------------------------------------------------------------------------
test_summary
