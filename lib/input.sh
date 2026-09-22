#!/bin/bash
# =============================================================================
# nano-whale :: lib/input.sh
# Keyboard input handler — reads key presses and dispatches actions
# =============================================================================

# ---------------------------------------------------------------------------
# Read a single keypress (non-blocking with timeout)
# Returns the key in variable KEY
# ---------------------------------------------------------------------------
KEY=""
KEY_SEQ=""

read_key() {
  KEY=""
  KEY_SEQ=""

  local char=""
  if ! IFS= read -rsn1 -t "${NW_INPUT_TIMEOUT:-0.05}" char; then
    return 1   # timeout — no key pressed
  fi

  # Escape sequence?
  if [[ "$char" == $'\033' ]]; then
    local seq1="" seq2="" seq3="" discard=""
    # ANSI sequences are already buffered by the terminal. Keep these reads
    # short so a lone Escape never stalls navigation.
    IFS= read -rsn1 -t 0.003 seq1 || true
    IFS= read -rsn1 -t 0.003 seq2 || true

    if [[ "$seq1" == "[" ]]; then
      case "$seq2" in
        A) KEY="UP" ;;
        B) KEY="DOWN" ;;
        C) KEY="RIGHT" ;;
        D) KEY="LEFT" ;;
        H) KEY="HOME" ;;
        F) KEY="END" ;;
        5) IFS= read -rsn1 -t 0.003 seq3 || true; KEY="PAGEUP" ;;
        6) IFS= read -rsn1 -t 0.003 seq3 || true; KEY="PAGEDOWN" ;;
        1)
          IFS= read -rsn1 -t 0.003 seq3 || true
          case "$seq3" in
            5) IFS= read -rsn1 -t 0.003 discard || true; KEY="F5" ;;   # ^[[15~
            ~) KEY="HOME" ;;
          esac
          ;;
        4) IFS= read -rsn1 -t 0.003 seq3 || true; KEY="END" ;;
        *)
          KEY="ESC"
          KEY_SEQ="$seq1$seq2"
          ;;
      esac
    elif [[ "$seq1" == "O" ]]; then
      case "$seq2" in
        H) KEY="HOME" ;;
        F) KEY="END" ;;
        *) KEY="ESC" ;;
      esac
    else
      KEY="ESC"
    fi
  elif [[ "$char" == $'\t' ]]; then
    KEY="TAB"
  elif [[ "$char" == "" ]]; then
    KEY="ENTER"
  elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\b' ]]; then
    KEY="BACKSPACE"
  elif [[ "$char" == $'\x01' ]]; then
    KEY="CTRL_A"
  elif [[ "$char" == $'\x04' ]]; then
    KEY="CTRL_D"
  elif [[ "$char" == $'\x0c' ]]; then
    KEY="CTRL_L"
  elif [[ "$char" == $'\x14' ]]; then
    KEY="CTRL_T"
  elif [[ "$char" == $'\x03' ]]; then
    KEY="CTRL_C"
  else
    KEY="$char"
  fi

  return 0
}

# ---------------------------------------------------------------------------
# Dispatch key to appropriate handler based on focus and mode
# ---------------------------------------------------------------------------
handle_key() {
  local key="$1"

  # Global keys (always active when not in fullscreen)
  case "$key" in
    q|CTRL_C)
      NW_RUNNING=false
      return
      ;;
    F5)
      _NW_CONT_LAST_FILE=""
      _NW_IMG_LAST_FILE=""
      _NW_VOL_LAST_FILE=""
      _NW_NET_LAST_FILE=""
      _NW_CONT_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
      _NW_IMG_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
      _NW_VOL_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
      _NW_NET_LAST_CONTENT="$_NW_SNAPSHOT_SENTINEL"
      _NW_STATS_LAST_CONTENT=""
      clear_inspect_caches 2>/dev/null || true
      fetch_all
      set_notify "Refreshed" "green"
      NW_LAST_CONTAINER_REFRESH=$SECONDS
      NW_LAST_MISC_REFRESH=$SECONDS
      return
      ;;
    TAB)
      # Cycle focus: containers → images → volumes → networks → containers
      NW_FOCUS=$(( (NW_FOCUS + 1) % 4 ))
      return
      ;;
    RIGHT)
      NW_CURRENT_TAB=$(( (NW_CURRENT_TAB + 1) % NW_TAB_COUNT ))
      NW_CONTENT_SCROLL=0
      (( NW_CURRENT_TAB >= 2 )) && NW_DEFER_EXPENSIVE_RENDER=2
      return
      ;;
    LEFT)
      NW_CURRENT_TAB=$(( (NW_CURRENT_TAB - 1 + NW_TAB_COUNT) % NW_TAB_COUNT ))
      NW_CONTENT_SCROLL=0
      (( NW_CURRENT_TAB >= 2 )) && NW_DEFER_EXPENSIVE_RENDER=2
      return
      ;;
    2) NW_FOCUS=0; return ;;
    3) NW_FOCUS=1; return ;;
    4) NW_FOCUS=2; return ;;
    5) NW_FOCUS=3; return ;;
    a)
      NW_LOGS_AUTO_SCROLL=$(! $NW_LOGS_AUTO_SCROLL && echo true || echo false)
      if $NW_LOGS_AUTO_SCROLL; then
        set_notify "Auto-scroll: ON" "green"
      else
        set_notify "Auto-scroll: OFF" "yellow"
      fi
      return
      ;;
    PAGEUP)
      (( NW_CONTENT_SCROLL > 0 )) && (( NW_CONTENT_SCROLL -= 10 ))
      (( NW_CONTENT_SCROLL < 0 )) && NW_CONTENT_SCROLL=0
      NW_LOGS_AUTO_SCROLL=false
      return
      ;;
    PAGEDOWN)
      (( NW_CONTENT_SCROLL += 10 ))
      NW_LOGS_AUTO_SCROLL=false
      return
      ;;
  esac

  # Focus-specific navigation
  case "$NW_FOCUS" in
    0) handle_container_key "$key" ;;
    1) handle_image_key "$key" ;;
    2) handle_volume_key "$key" ;;
    3) handle_network_key "$key" ;;
  esac
}

# ---------------------------------------------------------------------------
# Container-focused keys
# ---------------------------------------------------------------------------
handle_container_key() {
  local key="$1"
  local count=${#CONT_NAMES[@]}
  (( count == 0 )) && return

  case "$key" in
    UP)
      (( NW_SEL_CONTAINER > 0 )) && (( NW_SEL_CONTAINER-- ))
      ;;
    DOWN)
      (( NW_SEL_CONTAINER < count - 1 )) && (( NW_SEL_CONTAINER++ ))
      ;;
    HOME)
      NW_SEL_CONTAINER=0
      ;;
    END)
      NW_SEL_CONTAINER=$(( count - 1 ))
      ;;
    s)
      handle_container_start_stop
      ;;
    r)
      handle_container_restart
      ;;
    d)
      handle_container_delete
      ;;
    m)
      # Toggle mark
      local name="${CONT_NAMES[$NW_SEL_CONTAINER]}"
      if [[ -n "${MARKED_CONTAINERS[$name]:-}" ]]; then
        unset "MARKED_CONTAINERS[$name]"
      else
        MARKED_CONTAINERS["$name"]=1
      fi
      ;;
    CTRL_A)
      handle_select_all_containers
      ;;
    t)
      handle_exec_container
      ;;
    l)
      handle_fullscreen_logs
      ;;
    CTRL_T)
      handle_exec_new_window
      ;;
    CTRL_L)
      handle_logs_new_window
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Image-focused keys
# ---------------------------------------------------------------------------
handle_image_key() {
  local key="$1"
  local count=${#IMG_REPOS[@]}
  (( count == 0 )) && return

  case "$key" in
    UP)   (( NW_SEL_IMAGE > 0 )) && (( NW_SEL_IMAGE-- )) ;;
    DOWN) (( NW_SEL_IMAGE < count - 1 )) && (( NW_SEL_IMAGE++ )) ;;
    HOME) NW_SEL_IMAGE=0 ;;
    END)  NW_SEL_IMAGE=$(( count - 1 )) ;;
    m)
      local id="${IMG_IDS[$NW_SEL_IMAGE]}"
      if [[ -n "${MARKED_IMAGES[$id]:-}" ]]; then
        unset "MARKED_IMAGES[$id]"
      else
        MARKED_IMAGES["$id"]=1
      fi
      ;;
    CTRL_A)
      if (( ${#MARKED_IMAGES[@]} == count )); then
        MARKED_IMAGES=()
        set_notify "Deselected all images" "yellow"
      else
        local i
        for (( i=0; i<count; i++ )); do
          MARKED_IMAGES["${IMG_IDS[$i]}"]=1
        done
        set_notify "Selected $count images" "green"
      fi
      ;;
    d)
      handle_image_delete
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Volume-focused keys
# ---------------------------------------------------------------------------
handle_volume_key() {
  local key="$1"
  local count=${#VOL_NAMES[@]}
  (( count == 0 )) && return

  case "$key" in
    UP)   (( NW_SEL_VOLUME > 0 )) && (( NW_SEL_VOLUME-- )) ;;
    DOWN) (( NW_SEL_VOLUME < count - 1 )) && (( NW_SEL_VOLUME++ )) ;;
    HOME) NW_SEL_VOLUME=0 ;;
    END)  NW_SEL_VOLUME=$(( count - 1 )) ;;
    m)
      local name="${VOL_NAMES[$NW_SEL_VOLUME]}"
      if [[ -n "${MARKED_VOLUMES[$name]:-}" ]]; then
        unset "MARKED_VOLUMES[$name]"
      else
        MARKED_VOLUMES["$name"]=1
      fi
      ;;
    CTRL_A)
      if (( ${#MARKED_VOLUMES[@]} == count )); then
        MARKED_VOLUMES=()
        set_notify "Deselected all volumes" "yellow"
      else
        local i
        for (( i=0; i<count; i++ )); do
          MARKED_VOLUMES["${VOL_NAMES[$i]}"]=1
        done
        set_notify "Selected $count volumes" "green"
      fi
      ;;
    d)
      handle_volume_delete
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Network-focused keys
# ---------------------------------------------------------------------------
handle_network_key() {
  local key="$1"
  local count=${#NET_NAMES[@]}
  (( count == 0 )) && return

  case "$key" in
    UP)   (( NW_SEL_NETWORK > 0 )) && (( NW_SEL_NETWORK-- )) ;;
    DOWN) (( NW_SEL_NETWORK < count - 1 )) && (( NW_SEL_NETWORK++ )) ;;
    HOME) NW_SEL_NETWORK=0 ;;
    END)  NW_SEL_NETWORK=$(( count - 1 )) ;;
    d)
      local name="${NET_NAMES[$NW_SEL_NETWORK]}"
      action_delete_network "$name"
      fetch_networks
      (( NW_SEL_NETWORK >= ${#NET_NAMES[@]} )) && NW_SEL_NETWORK=$(( ${#NET_NAMES[@]} - 1 ))
      (( NW_SEL_NETWORK < 0 )) && NW_SEL_NETWORK=0
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Container action handlers
# ---------------------------------------------------------------------------
handle_container_start_stop() {
  if (( ${#MARKED_CONTAINERS[@]} > 0 )); then
    local name
    for name in "${!MARKED_CONTAINERS[@]}"; do
      local i
      for (( i=0; i<${#CONT_NAMES[@]}; i++ )); do
        if [[ "${CONT_NAMES[$i]}" == "$name" ]]; then
          action_toggle_container "$name" "${CONT_STATES[$i]}"
          break
        fi
      done
    done
    MARKED_CONTAINERS=()
    fetch_containers
  else
    local name="${CONT_NAMES[$NW_SEL_CONTAINER]}"
    local state="${CONT_STATES[$NW_SEL_CONTAINER]}"
    action_toggle_container "$name" "$state"
    fetch_containers
  fi
}

handle_container_restart() {
  if (( ${#MARKED_CONTAINERS[@]} > 0 )); then
    local name
    for name in "${!MARKED_CONTAINERS[@]}"; do
      local i
      for (( i=0; i<${#CONT_NAMES[@]}; i++ )); do
        if [[ "${CONT_NAMES[$i]}" == "$name" && "${CONT_STATES[$i]}" == "running" ]]; then
          action_restart_container "$name"
          break
        fi
      done
    done
    MARKED_CONTAINERS=()
    fetch_containers
  else
    local name="${CONT_NAMES[$NW_SEL_CONTAINER]}"
    local state="${CONT_STATES[$NW_SEL_CONTAINER]}"
    [[ "$state" == "running" ]] && action_restart_container "$name" && fetch_containers
  fi
}

handle_container_delete() {
  if (( ${#MARKED_CONTAINERS[@]} > 0 )); then
    local count=${#MARKED_CONTAINERS[@]}
    printf '\033[?25h'
    tui_goto $(( TERM_ROWS / 2 )) $(( TERM_COLS / 2 - 20 ))
    printf '%b Delete %d container(s)? [y/N] %b' "${COLOR[red]}${COLOR[bold]}" "$count" "${COLOR[reset]}"
    local ans
    IFS= read -rsn1 ans
    printf '\033[?25l'
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      local name
      for name in "${!MARKED_CONTAINERS[@]}"; do
        action_delete_container "$name"
      done
      MARKED_CONTAINERS=()
      fetch_containers
      (( NW_SEL_CONTAINER >= ${#CONT_NAMES[@]} )) && NW_SEL_CONTAINER=$(( ${#CONT_NAMES[@]} - 1 ))
      (( NW_SEL_CONTAINER < 0 )) && NW_SEL_CONTAINER=0
    fi
  else
    local name="${CONT_NAMES[$NW_SEL_CONTAINER]}"
    printf '\033[?25h'
    tui_goto $(( TERM_ROWS / 2 )) $(( TERM_COLS / 2 - 20 ))
    printf '%b Delete container %s? [y/N] %b' "${COLOR[red]}${COLOR[bold]}" "$name" "${COLOR[reset]}"
    local ans
    IFS= read -rsn1 ans
    printf '\033[?25l'
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      action_delete_container "$name"
      fetch_containers
      (( NW_SEL_CONTAINER >= ${#CONT_NAMES[@]} )) && NW_SEL_CONTAINER=$(( ${#CONT_NAMES[@]} - 1 ))
      (( NW_SEL_CONTAINER < 0 )) && NW_SEL_CONTAINER=0
    fi
  fi
}

handle_image_delete() {
  if (( ${#MARKED_IMAGES[@]} > 0 )); then
    local count=${#MARKED_IMAGES[@]}
    printf '\033[?25h'
    tui_goto $(( TERM_ROWS / 2 )) $(( TERM_COLS / 2 - 20 ))
    printf '%b Delete %d image(s)? [y/N] %b' "${COLOR[red]}${COLOR[bold]}" "$count" "${COLOR[reset]}"
    local ans
    IFS= read -rsn1 ans
    printf '\033[?25l'
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      local id
      for id in "${!MARKED_IMAGES[@]}"; do
        action_delete_image "$id"
      done
      MARKED_IMAGES=()
      fetch_images
      (( NW_SEL_IMAGE >= ${#IMG_REPOS[@]} )) && NW_SEL_IMAGE=$(( ${#IMG_REPOS[@]} - 1 ))
      (( NW_SEL_IMAGE < 0 )) && NW_SEL_IMAGE=0
    fi
  else
    local id="${IMG_IDS[$NW_SEL_IMAGE]}"
    local repo="${IMG_REPOS[$NW_SEL_IMAGE]}"
    local tag="${IMG_TAGS[$NW_SEL_IMAGE]}"
    printf '\033[?25h'
    tui_goto $(( TERM_ROWS / 2 )) $(( TERM_COLS / 2 - 20 ))
    printf '%b Delete image %s:%s? [y/N] %b' "${COLOR[red]}${COLOR[bold]}" "$repo" "$tag" "${COLOR[reset]}"
    local ans
    IFS= read -rsn1 ans
    printf '\033[?25l'
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      action_delete_image "$id"
      fetch_images
      (( NW_SEL_IMAGE >= ${#IMG_REPOS[@]} )) && NW_SEL_IMAGE=$(( ${#IMG_REPOS[@]} - 1 ))
      (( NW_SEL_IMAGE < 0 )) && NW_SEL_IMAGE=0
    fi
  fi
}

handle_volume_delete() {
  if (( ${#MARKED_VOLUMES[@]} > 0 )); then
    local count=${#MARKED_VOLUMES[@]}
    printf '\033[?25h'
    tui_goto $(( TERM_ROWS / 2 )) $(( TERM_COLS / 2 - 20 ))
    printf '%b Delete %d volume(s)? [y/N] %b' "${COLOR[red]}${COLOR[bold]}" "$count" "${COLOR[reset]}"
    local ans
    IFS= read -rsn1 ans
    printf '\033[?25l'
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      local name
      for name in "${!MARKED_VOLUMES[@]}"; do
        action_delete_volume "$name"
      done
      MARKED_VOLUMES=()
      fetch_volumes
      (( NW_SEL_VOLUME >= ${#VOL_NAMES[@]} )) && NW_SEL_VOLUME=$(( ${#VOL_NAMES[@]} - 1 ))
      (( NW_SEL_VOLUME < 0 )) && NW_SEL_VOLUME=0
    fi
  else
    local name="${VOL_NAMES[$NW_SEL_VOLUME]}"
    printf '\033[?25h'
    tui_goto $(( TERM_ROWS / 2 )) $(( TERM_COLS / 2 - 20 ))
    printf '%b Delete volume %s? [y/N] %b' "${COLOR[red]}${COLOR[bold]}" "$name" "${COLOR[reset]}"
    local ans
    IFS= read -rsn1 ans
    printf '\033[?25l'
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      action_delete_volume "$name"
      fetch_volumes
      (( NW_SEL_VOLUME >= ${#VOL_NAMES[@]} )) && NW_SEL_VOLUME=$(( ${#VOL_NAMES[@]} - 1 ))
      (( NW_SEL_VOLUME < 0 )) && NW_SEL_VOLUME=0
    fi
  fi
}

handle_select_all_containers() {
  local count=${#CONT_NAMES[@]}
  if (( ${#MARKED_CONTAINERS[@]} == count )); then
    MARKED_CONTAINERS=()
    set_notify "Deselected all containers" "yellow"
  else
    local i
    for (( i=0; i<count; i++ )); do
      MARKED_CONTAINERS["${CONT_NAMES[$i]}"]=1
    done
    set_notify "Selected $count containers" "green"
  fi
}
