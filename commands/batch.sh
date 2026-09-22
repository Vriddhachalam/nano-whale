#!/bin/bash
# =============================================================================
# nano-whale :: commands/batch.sh
# Batch operations on marked items
# (Most batch logic is in input.sh handlers; this provides shared helpers)
# =============================================================================

# ---------------------------------------------------------------------------
# Get count of marked items for the currently focused panel
# ---------------------------------------------------------------------------
get_marked_count() {
  case "$NW_FOCUS" in
    0) echo "${#MARKED_CONTAINERS[@]}" ;;
    1) echo "${#MARKED_IMAGES[@]}" ;;
    2) echo "${#MARKED_VOLUMES[@]}" ;;
    *) echo "0" ;;
  esac
}

# ---------------------------------------------------------------------------
# Clear all marks for the currently focused panel
# ---------------------------------------------------------------------------
clear_marks() {
  case "$NW_FOCUS" in
    0) MARKED_CONTAINERS=() ;;
    1) MARKED_IMAGES=() ;;
    2) MARKED_VOLUMES=() ;;
  esac
}

# ---------------------------------------------------------------------------
# Is a specific item marked?
# ---------------------------------------------------------------------------
is_container_marked() {
  [[ -n "${MARKED_CONTAINERS[$1]:-}" ]]
}

is_image_marked() {
  [[ -n "${MARKED_IMAGES[$1]:-}" ]]
}

is_volume_marked() {
  [[ -n "${MARKED_VOLUMES[$1]:-}" ]]
}
