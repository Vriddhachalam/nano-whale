#!/bin/bash
# =============================================================================
# nano-whale :: tests/run_tests.sh
# Test runner — executes all test files
# =============================================================================
set -Euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

printf '\n🐳 nano-whale Test Suite\n'
printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'

total_passed=0
total_failed=0
total_run=0
failed_suites=()

run_test_file() {
  local test_file="$1"
  local name
  name="$(basename "$test_file" .sh)"

  printf '\n📋 Running: %s\n' "$name"

  local output
  local exit_code=0
  output=$(bash "$test_file" 2>&1) || exit_code=$?

  printf '%s\n' "$output"

  # Extract counts from output
  local tests_line
  tests_line=$(echo "$output" | grep -oP 'Tests:\s+\K\d+' | head -1 || echo "0")
  local passed_line
  passed_line=$(echo "$output" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
  local failed_line
  failed_line=$(echo "$output" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")

  total_run=$(( total_run + tests_line ))
  total_passed=$(( total_passed + passed_line ))
  total_failed=$(( total_failed + failed_line ))

  if (( exit_code != 0 )); then
    failed_suites+=("$name")
  fi
}

# Discover and run all test files
for test_file in "$SCRIPT_DIR"/test_*.sh; do
  [[ "$(basename "$test_file")" == "test_utils.sh" ]] && continue
  [[ -f "$test_file" ]] || continue
  run_test_file "$test_file"
done

# Final summary
printf '\n\n🏁 Overall Results\n'
printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
printf 'Total:  %d tests, \033[32m%d passed\033[0m, \033[31m%d failed\033[0m\n' \
  "$total_run" "$total_passed" "$total_failed"

if (( ${#failed_suites[@]} > 0 )); then
  printf '\n\033[31mFailed suites:\033[0m\n'
  for suite in "${failed_suites[@]}"; do
    printf '  • %s\n' "$suite"
  done
  exit 1
fi

printf '\n\033[32m✅ All test suites passed!\033[0m\n'
exit 0
