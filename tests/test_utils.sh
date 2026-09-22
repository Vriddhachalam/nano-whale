#!/bin/bash
# =============================================================================
# nano-whale :: tests/test_utils.sh
# Minimal test framework for Bash
# =============================================================================

_TESTS_RUN=0
_TESTS_PASSED=0
_TESTS_FAILED=0
_TEST_FAILURES=()

# Colors
_T_RED='\033[31m'
_T_GREEN='\033[32m'
_T_YELLOW='\033[33m'
_T_RESET='\033[0m'
_T_BOLD='\033[1m'

# ---------------------------------------------------------------------------
# Assert functions
# ---------------------------------------------------------------------------
assert_equals() {
  local expected="$1"
  local actual="$2"
  local msg="${3:-assert_equals}"
  (( _TESTS_RUN++ ))

  if [[ "$expected" == "$actual" ]]; then
    (( _TESTS_PASSED++ ))
    printf '  %b✓%b %s\n' "$_T_GREEN" "$_T_RESET" "$msg"
  else
    (( _TESTS_FAILED++ ))
    _TEST_FAILURES+=("$msg: expected='$expected' actual='$actual'")
    printf '  %b✗%b %s\n' "$_T_RED" "$_T_RESET" "$msg"
    printf '    expected: %s\n' "$expected"
    printf '    actual:   %s\n' "$actual"
  fi
}

assert_not_empty() {
  local value="$1"
  local msg="${2:-assert_not_empty}"
  (( _TESTS_RUN++ ))

  if [[ -n "$value" ]]; then
    (( _TESTS_PASSED++ ))
    printf '  %b✓%b %s\n' "$_T_GREEN" "$_T_RESET" "$msg"
  else
    (( _TESTS_FAILED++ ))
    _TEST_FAILURES+=("$msg: value was empty")
    printf '  %b✗%b %s (value was empty)\n' "$_T_RED" "$_T_RESET" "$msg"
  fi
}

assert_empty() {
  local value="$1"
  local msg="${2:-assert_empty}"
  (( _TESTS_RUN++ ))

  if [[ -z "$value" ]]; then
    (( _TESTS_PASSED++ ))
    printf '  %b✓%b %s\n' "$_T_GREEN" "$_T_RESET" "$msg"
  else
    (( _TESTS_FAILED++ ))
    _TEST_FAILURES+=("$msg: value='$value' (expected empty)")
    printf '  %b✗%b %s (value='%s')\n' "$_T_RED" "$_T_RESET" "$msg" "$value"
  fi
}

assert_true() {
  local condition="$1"
  local msg="${2:-assert_true}"
  (( _TESTS_RUN++ ))

  if eval "$condition" 2>/dev/null; then
    (( _TESTS_PASSED++ ))
    printf '  %b✓%b %s\n' "$_T_GREEN" "$_T_RESET" "$msg"
  else
    (( _TESTS_FAILED++ ))
    _TEST_FAILURES+=("$msg: condition '$condition' was false")
    printf '  %b✗%b %s\n' "$_T_RED" "$_T_RESET" "$msg"
  fi
}

assert_exit_code() {
  local expected_code="$1"
  shift
  local msg="${*: -1}"
  local cmd_args=("${@:1:$#-1}")
  (( _TESTS_RUN++ ))

  "${cmd_args[@]}" >/dev/null 2>&1
  local actual_code=$?

  if (( actual_code == expected_code )); then
    (( _TESTS_PASSED++ ))
    printf '  %b✓%b %s\n' "$_T_GREEN" "$_T_RESET" "$msg"
  else
    (( _TESTS_FAILED++ ))
    _TEST_FAILURES+=("$msg: expected exit $expected_code, got $actual_code")
    printf '  %b✗%b %s (expected exit %d, got %d)\n' "$_T_RED" "$_T_RESET" "$msg" "$expected_code" "$actual_code"
  fi
}

# ---------------------------------------------------------------------------
# Test grouping
# ---------------------------------------------------------------------------
describe() {
  printf '\n%b%b%s%b\n' "$_T_BOLD" "$_T_YELLOW" "$1" "$_T_RESET"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
test_summary() {
  printf '\n%b━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%b\n' "$_T_BOLD" "$_T_RESET"
  printf 'Tests:  %d total, ' "$_TESTS_RUN"
  printf '%b%d passed%b, ' "$_T_GREEN" "$_TESTS_PASSED" "$_T_RESET"
  printf '%b%d failed%b\n' "$_T_RED" "$_TESTS_FAILED" "$_T_RESET"

  if (( _TESTS_FAILED > 0 )); then
    printf '\n%bFailures:%b\n' "$_T_RED" "$_T_RESET"
    local f
    for f in "${_TEST_FAILURES[@]}"; do
      printf '  • %s\n' "$f"
    done
    return 1
  fi

  printf '%b\nAll tests passed!%b\n' "$_T_GREEN" "$_T_RESET"
  return 0
}
