#!/bin/bash
# =============================================================================
# nano-whale :: INSTALL.sh
# Universal installer for nano-whale (Bash edition)
# =============================================================================
set -Euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

printf '🐳 Installing nano-whale...\n\n'

# ---------------------------------------------------------------------------
# Check Bash version
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
  printf 'ERROR: nano-whale requires Bash 4.3+ (you have %s)\n' "$BASH_VERSION" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Check Docker
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  printf 'WARNING: Docker is not installed or not in PATH.\n' >&2
  printf '         nano-whale requires Docker to function.\n' >&2
fi

# ---------------------------------------------------------------------------
# Make scripts executable
# ---------------------------------------------------------------------------
chmod +x "$SCRIPT_DIR/nano-whale.sh"
chmod +x "$SCRIPT_DIR/lib/"*.sh 2>/dev/null || true
chmod +x "$SCRIPT_DIR/commands/"*.sh 2>/dev/null || true
chmod +x "$SCRIPT_DIR/tests/"*.sh 2>/dev/null || true

# ---------------------------------------------------------------------------
# Create install directory
# ---------------------------------------------------------------------------
mkdir -p "$INSTALL_DIR"

# ---------------------------------------------------------------------------
# Create wrapper script that sources from the install location
# ---------------------------------------------------------------------------
INSTALL_SRC="$HOME/.nano-whale"

# Copy project
if [[ "$SCRIPT_DIR" != "$INSTALL_SRC" ]]; then
  rm -rf "$INSTALL_SRC"
  cp -r "$SCRIPT_DIR" "$INSTALL_SRC"
  chmod +x "$INSTALL_SRC/nano-whale.sh"
fi

# Create symlink or wrapper
if [[ -w "$INSTALL_DIR" ]]; then
  ln -sf "$INSTALL_SRC/nano-whale.sh" "$INSTALL_DIR/nano-whale"
  printf '✅ Installed nano-whale to %s/nano-whale\n' "$INSTALL_DIR"
else
  sudo ln -sf "$INSTALL_SRC/nano-whale.sh" "$INSTALL_DIR/nano-whale" 2>/dev/null || {
    printf 'Could not create symlink in %s\n' "$INSTALL_DIR" >&2
    printf 'Add this to your shell profile:\n' >&2
    printf '  export PATH="%s:$PATH"\n' "$INSTALL_SRC" >&2
    printf '  alias nano-whale="%s/nano-whale.sh"\n' "$INSTALL_SRC" >&2
  }
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
if command -v nano-whale >/dev/null 2>&1; then
  printf '\n🎉 Installation complete! Run: nano-whale\n'
else
  printf '\n📋 Installation complete. Run: %s/nano-whale.sh\n' "$INSTALL_SRC"
  printf '   Or add %s to your PATH.\n' "$INSTALL_DIR"
fi

printf '\nDependencies:\n'
printf '  ✅ bash %s\n' "$BASH_VERSION"
printf '  %s docker\n' "$(command -v docker >/dev/null 2>&1 && echo '✅' || echo '❌')"
printf '  %s jq (optional, for formatted inspection)\n' "$(command -v jq >/dev/null 2>&1 && echo '✅' || echo '⚠️ ')"
