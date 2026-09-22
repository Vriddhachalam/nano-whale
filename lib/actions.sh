#!/bin/bash
# =============================================================================
# nano-whale :: lib/actions.sh
# Container, image, volume, and network actions
# =============================================================================

# ---------------------------------------------------------------------------
# Container actions
# ---------------------------------------------------------------------------
action_start_container() {
  local name="$1"
  if docker_exec_args 30 start "$name" >/dev/null 2>&1; then
    set_notify "Started $name" "green"
  else
    set_notify "Failed to start $name" "red"
  fi
}

action_stop_container() {
  local name="$1"
  if docker_exec_args 30 stop "$name" >/dev/null 2>&1; then
    set_notify "Stopped $name" "yellow"
  else
    set_notify "Failed to stop $name" "red"
  fi
}

action_restart_container() {
  local name="$1"
  # Docker restart can block while a container's stop timeout elapses. Run it
  # outside the UI loop so navigation remains responsive.
  nw_run_with_timeout 60 "$DOCKER_CMD" restart "$name" >/dev/null 2>&1 &
  local pid=$!
  _NW_ACTION_PIDS+=("$pid")
  set_notify "Restarting $name..." "yellow"
}

action_delete_container() {
  local name="$1"
  if docker_exec_args 30 rm -f "$name" >/dev/null 2>&1; then
    set_notify "Deleted container $name" "red"
  else
    set_notify "Failed to delete container $name" "red"
  fi
}

# ---------------------------------------------------------------------------
# Image actions
# ---------------------------------------------------------------------------
action_delete_image() {
  local id="$1"
  if docker_exec_args 30 rmi -f "$id" >/dev/null 2>&1; then
    set_notify "Deleted image $id" "yellow"
  else
    set_notify "Failed to delete image $id" "red"
  fi
}

# ---------------------------------------------------------------------------
# Volume actions
# ---------------------------------------------------------------------------
action_delete_volume() {
  local name="$1"
  if docker_exec_args 30 volume rm -f "$name" >/dev/null 2>&1; then
    set_notify "Deleted volume $name" "magenta"
  else
    set_notify "Failed to delete volume $name" "red"
  fi
}

# ---------------------------------------------------------------------------
# Network actions
# ---------------------------------------------------------------------------
action_delete_network() {
  local name="$1"
  # Prevent deletion of system networks
  case "$name" in
    bridge|host|none)
      set_notify "Cannot delete '$name' — system network" "yellow"
      return 1
      ;;
  esac

  if docker_exec_args 30 network rm "$name" >/dev/null 2>&1; then
    set_notify "Deleted network $name" "yellow"
  else
    set_notify "Failed to delete network $name" "red"
  fi
}

# ---------------------------------------------------------------------------
# Toggle container start/stop
# ---------------------------------------------------------------------------
action_toggle_container() {
  local name="$1"
  local state="$2"
  if [[ "$state" == "running" ]]; then
    action_stop_container "$name"
  else
    action_start_container "$name"
  fi
}

# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------
set_notify() {
  NW_NOTIFY_MSG="$1"
  NW_NOTIFY_COLOR="$2"
  NW_NOTIFY_UNTIL=$(( SECONDS + 3 ))
}
