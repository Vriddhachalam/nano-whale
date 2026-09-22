#!/bin/bash
# =============================================================================
# nano-whale :: uninstall.sh
# Remove nano-whale installation
# =============================================================================
set -Euo pipefail

printf '🐳 Uninstalling nano-whale...\n'

# Remove symlinks
for dir in "$HOME/.local/bin" "/usr/local/bin"; do
  if [[ -L "$dir/nano-whale" ]]; then
    rm -f "$dir/nano-whale" 2>/dev/null || sudo rm -f "$dir/nano-whale" 2>/dev/null || true
    printf '  Removed %s/nano-whale\n' "$dir"
  fi
done

# Remove installed copy
if [[ -d "$HOME/.nano-whale" ]]; then
  rm -rf "$HOME/.nano-whale"
  printf '  Removed %s/.nano-whale\n' "$HOME"
fi

printf '\n✅ nano-whale has been uninstalled.\n'
