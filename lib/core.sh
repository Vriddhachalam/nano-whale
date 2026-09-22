#!/bin/bash
# =============================================================================
# nano-whale :: lib/core.sh
# Global state, constants, and shared data structures
# =============================================================================

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
NW_VERSION="2.0.0"

# ---------------------------------------------------------------------------
# Tab names and indices
# ---------------------------------------------------------------------------
TAB_NAMES=("Logs" "Stats" "Env" "Config" "Top")
NW_CURRENT_TAB=0
NW_TAB_COUNT=${#TAB_NAMES[@]}

# ---------------------------------------------------------------------------
# Container data  (parallel arrays — Bash doesn't have structs)
#   Index i → CONT_NAMES[i], CONT_STATUS[i], CONT_IDS[i], etc.
# ---------------------------------------------------------------------------
declare -a CONT_NAMES=()
declare -a CONT_STATUS=()
declare -a CONT_IDS=()
declare -a CONT_IMAGES=()
declare -a CONT_PORTS=()
declare -a CONT_STATES=()

# ---------------------------------------------------------------------------
# Image data
# ---------------------------------------------------------------------------
declare -a IMG_REPOS=()
declare -a IMG_TAGS=()
declare -a IMG_SIZES=()
declare -a IMG_IDS=()

# ---------------------------------------------------------------------------
# Volume data
# ---------------------------------------------------------------------------
declare -a VOL_DRIVERS=()
declare -a VOL_NAMES=()

# ---------------------------------------------------------------------------
# Network data
# ---------------------------------------------------------------------------
declare -a NET_DRIVERS=()
declare -a NET_NAMES=()

# ---------------------------------------------------------------------------
# Stats data  (associative arrays keyed by container name)
# ---------------------------------------------------------------------------
declare -A STAT_CPU=()
declare -A STAT_MEM=()
declare -A STAT_MEM_USAGE=()
declare -A STAT_NET_IO=()
declare -A STAT_BLOCK_IO=()
declare -A STAT_PIDS=()

# CPU/Memory history for charts (stored as space-separated values per container)
declare -A CPU_HISTORY=()
declare -A MEM_HISTORY=()
MAX_HISTORY=40

# ---------------------------------------------------------------------------
# Selection indices
# ---------------------------------------------------------------------------
NW_SEL_CONTAINER=0
NW_SEL_IMAGE=0
NW_SEL_VOLUME=0
NW_SEL_NETWORK=0

# ---------------------------------------------------------------------------
# Focus: which panel has focus
#   0=containers, 1=images, 2=volumes, 3=networks
# ---------------------------------------------------------------------------
NW_FOCUS=0

# ---------------------------------------------------------------------------
# Marks for multi-select (space-separated names/ids)
# ---------------------------------------------------------------------------
declare -A MARKED_CONTAINERS=()
declare -A MARKED_IMAGES=()
declare -A MARKED_VOLUMES=()

# ---------------------------------------------------------------------------
# Logs state
# ---------------------------------------------------------------------------
NW_LOGS_CONTENT=""
NW_LOGS_AUTO_SCROLL=true
NW_LOGS_CONTAINER=""
_NW_LOGS_PID=""
_NW_LOGS_FIFO=""
_NW_LOGS_PENDING=false
declare -a _NW_ACTION_PIDS=()

# ---------------------------------------------------------------------------
# Stats process
# ---------------------------------------------------------------------------
_NW_STATS_PID=""
_NW_STATS_FIFO=""

# ---------------------------------------------------------------------------
# Fullscreen mode
# ---------------------------------------------------------------------------
NW_FULLSCREEN=false

# ---------------------------------------------------------------------------
# Refresh timers (using SECONDS)
# ---------------------------------------------------------------------------
NW_LAST_CONTAINER_REFRESH=0
NW_LAST_MISC_REFRESH=0
NW_CONTAINER_INTERVAL=3
NW_MISC_INTERVAL=15

# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------
NW_NOTIFY_MSG=""
NW_NOTIFY_COLOR=""
NW_NOTIFY_UNTIL=0

# ---------------------------------------------------------------------------
# Scroll offsets for the content pane
# ---------------------------------------------------------------------------
NW_CONTENT_SCROLL=0
NW_CONTENT_LINES=0
_TUI_FIT_RESULT=""

# ---------------------------------------------------------------------------
# Running flag
# ---------------------------------------------------------------------------
NW_RUNNING=true
NW_DATA_CHANGED=false
NW_NEEDS_RENDER=true
NW_DEFER_EXPENSIVE_RENDER=0

# ---------------------------------------------------------------------------
# Terminal dimensions (updated on SIGWINCH)
# ---------------------------------------------------------------------------
TERM_ROWS=24
TERM_COLS=80

update_term_size() {
  TERM_ROWS=$(tput lines 2>/dev/null || echo 24)
  TERM_COLS=$(tput cols  2>/dev/null || echo 80)
}
