#!/bin/bash
# =============================================================================
# nano-whale :: config/defaults.sh
# Default configuration values
# =============================================================================

# Refresh intervals (seconds)
NW_CONTAINER_INTERVAL=3
NW_MISC_INTERVAL=5
NW_STATS_INTERVAL=2
# Keep keyboard response snappy without spinning the main loop at 100Hz.
NW_INPUT_TIMEOUT=0.05
NW_INPUT_BATCH_MAX=16

# Logs
NW_LOGS_TAIL_DEFAULT=100
NW_LOGS_MAX_LINES=500

# Stats
MAX_HISTORY=40

# Chart width
NW_CHART_WIDTH=50
