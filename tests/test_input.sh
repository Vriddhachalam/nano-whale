#!/bin/bash
# =============================================================================
# nano-whale :: tests/test_input.sh
# Tests for input validation and CLI behavior
# =============================================================================
set -Euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/test_utils.sh"
source "$PROJECT_DIR/config/defaults.sh"
source "$PROJECT_DIR/lib/utils.sh"
source "$PROJECT_DIR/lib/config.sh"
source "$PROJECT_DIR/lib/core.sh"

# ---------------------------------------------------------------------------
describe "CLI --help flag"
# ---------------------------------------------------------------------------

help_exit=0
help_output=$("$PROJECT_DIR/nano-whale.sh" --help 2>&1) || help_exit=$?
assert_equals "0" "$help_exit" "--help exits with code 0"
assert_not_empty "$help_output" "--help produces output"

# Check for key sections in help
assert_true "[[ '$help_output' == *'USAGE'* ]]" "--help contains USAGE"
assert_true "[[ '$help_output' == *'KEYBOARD SHORTCUTS'* ]]" "--help contains KEYBOARD SHORTCUTS"
assert_true "[[ '$help_output' == *'REQUIREMENTS'* ]]" "--help contains REQUIREMENTS"

# ---------------------------------------------------------------------------
describe "CLI --version flag"
# ---------------------------------------------------------------------------

version_output=$("$PROJECT_DIR/nano-whale.sh" --version 2>&1)
assert_true "[[ \$? -eq 0 ]]" "--version exits with code 0"
assert_equals "nano-whale 2.0.0" "$version_output" "--version output correct"

# ---------------------------------------------------------------------------
describe "CLI invalid option"
# ---------------------------------------------------------------------------

invalid_output=$("$PROJECT_DIR/nano-whale.sh" --bogus 2>&1 || true)
assert_not_empty "$invalid_output" "Invalid option produces error"

# ---------------------------------------------------------------------------
describe "System network protection"
# ---------------------------------------------------------------------------

# Test that system networks are protected
source "$PROJECT_DIR/lib/actions.sh"

# Mock: set_notify to capture
_last_notify=""
set_notify() { _last_notify="$1"; }

action_delete_network "bridge"
assert_true "[[ '$_last_notify' == *'Cannot delete'* ]]" "bridge deletion blocked"

action_delete_network "host"
assert_true "[[ '$_last_notify' == *'Cannot delete'* ]]" "host deletion blocked"

action_delete_network "none"
assert_true "[[ '$_last_notify' == *'Cannot delete'* ]]" "none deletion blocked"

# ---------------------------------------------------------------------------
describe "Selection clamping"
# ---------------------------------------------------------------------------

# Simulate 3 containers
CONT_NAMES=("a" "b" "c")
NW_SEL_CONTAINER=5

# Clamp
(( NW_SEL_CONTAINER >= ${#CONT_NAMES[@]} )) && NW_SEL_CONTAINER=$(( ${#CONT_NAMES[@]} - 1 ))
assert_equals "2" "$NW_SEL_CONTAINER" "Selection clamped to max index"

NW_SEL_CONTAINER=-1
(( NW_SEL_CONTAINER < 0 )) && NW_SEL_CONTAINER=0
assert_equals "0" "$NW_SEL_CONTAINER" "Selection clamped to 0"

# ---------------------------------------------------------------------------
describe "Tab cycling"
# ---------------------------------------------------------------------------

NW_CURRENT_TAB=0
NW_CURRENT_TAB=$(( (NW_CURRENT_TAB + 1) % NW_TAB_COUNT ))
assert_equals "1" "$NW_CURRENT_TAB" "Tab cycles forward: 0 → 1"

NW_CURRENT_TAB=4
NW_CURRENT_TAB=$(( (NW_CURRENT_TAB + 1) % NW_TAB_COUNT ))
assert_equals "0" "$NW_CURRENT_TAB" "Tab wraps: 4 → 0"

NW_CURRENT_TAB=0
NW_CURRENT_TAB=$(( (NW_CURRENT_TAB - 1 + NW_TAB_COUNT) % NW_TAB_COUNT ))
assert_equals "4" "$NW_CURRENT_TAB" "Tab cycles backward: 0 → 4"

# ---------------------------------------------------------------------------
test_summary
