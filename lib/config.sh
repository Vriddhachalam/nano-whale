#!/bin/bash
# =============================================================================
# nano-whale :: lib/config.sh
# Platform detection and Docker command configuration
# =============================================================================

# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------
NW_PLATFORM="linux"
NW_IS_WSL=false

detect_platform() {
  local uname_s
  uname_s="$(uname -s 2>/dev/null || echo "Unknown")"

  case "$uname_s" in
    Linux*)
      NW_PLATFORM="linux"
      # Detect WSL
      if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
        NW_IS_WSL=true
      fi
      ;;
    Darwin*)  NW_PLATFORM="darwin" ;;
    MINGW*|MSYS*|CYGWIN*)
      NW_PLATFORM="windows"
      ;;
    *)
      NW_PLATFORM="unknown"
      warn "Unknown platform: $uname_s"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Docker command — on Windows (Git Bash) use "wsl docker", else "docker"
# ---------------------------------------------------------------------------
DOCKER_CMD="docker"

setup_docker_cmd() {
  if [[ "$NW_PLATFORM" == "windows" ]]; then
    if command -v docker.exe >/dev/null 2>&1; then
      DOCKER_CMD="docker.exe"
    else
      DOCKER_CMD="docker"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Verify Docker is accessible
# ---------------------------------------------------------------------------
check_docker() {
  if ! nw_run_with_timeout 3 "$DOCKER_CMD" version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Run both detections
# ---------------------------------------------------------------------------
init_config() {
  detect_platform
  setup_docker_cmd
}
