#!/bin/bash
# =============================================================================
# nano-whale :: examples/demo.sh
# Quick demo: shows how to use nano-whale
# =============================================================================
set -Euo pipefail

printf '🐳 nano-whale Demo\n'
printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'

printf 'nano-whale is a lightweight Docker TUI built in pure Bash.\n\n'

printf 'Quick Start:\n'
printf '  1. Make sure Docker is running\n'
printf '  2. Run: ./nano-whale.sh\n\n'

printf 'Example workflow:\n'
printf '  # Start some containers first\n'
printf '  docker run -d --name demo-nginx nginx\n'
printf '  docker run -d --name demo-redis redis\n\n'
printf '  # Launch nano-whale\n'
printf '  ./nano-whale.sh\n\n'

printf 'Key shortcuts:\n'
printf '  ↑↓        Navigate containers\n'
printf '  Tab       Switch between lists\n'
printf '  ←→        Switch tabs (Logs/Stats/Env/Config/Top)\n'
printf '  s         Start/Stop container\n'
printf '  t         Shell into container\n'
printf '  l         Fullscreen logs\n'
printf '  m         Mark for batch operations\n'
printf '  d         Delete selected\n'
printf '  q         Quit\n'
