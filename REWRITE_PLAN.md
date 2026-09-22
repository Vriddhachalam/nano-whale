# Nano-Whale: Rewrite Plan (Node.js → Bash)

## Summary

This project was originally implemented in **Node.js** (Bun runtime) using the **neo-blessed** TUI library, compiled into standalone binaries. It has been **completely rewritten in pure Bash** using ANSI escape codes for the terminal UI.

## What Changed

| Aspect | Original | Bash Rewrite |
|--------|----------|-------------|
| Runtime | Node.js (Bun) | Bash 4.0+ |
| TUI Framework | neo-blessed | Pure ANSI escape codes |
| Build System | `bun build --compile` | None (interpreted) |
| Distribution | Compiled binaries | Shell script |
| Dependencies | Bun, neo-blessed, node_modules | bash, docker, (optional) jq |
| File count | 1 monolithic JS file (1284 lines) | 12+ modular .sh files |

## Features Preserved

- ✅ Container management (list, start, stop, restart, delete)
- ✅ Image management (list, delete)
- ✅ Volume management (list, delete)
- ✅ Network management (list, delete with system protection)
- ✅ 5 tabs: Logs, Stats, Env, Config, Top
- ✅ Live log streaming
- ✅ Real-time CPU/Memory charts (sparkline)
- ✅ Exec into container shell
- ✅ Multi-select / batch operations
- ✅ Select-all toggle
- ✅ Fullscreen logs and exec modes
- ✅ New terminal window spawning (Linux/macOS)
- ✅ Auto-refresh (containers every 3s, misc every 15s)
- ✅ Delete confirmation dialogs
- ✅ Notification messages
- ✅ WSL/Windows detection
- ✅ All keyboard shortcuts preserved

## Known Differences

| Feature | Original | Bash Version |
|---------|----------|-------------|
| Mouse support | Full (click, scroll) | Not supported (keyboard only) |
| Charts | Braille dot patterns | Block characters (▁▂▃▄▅▆▇█) |
| Tab clicking | Mouse click on tab header | Arrow keys only |
| Notifications | Popup overlay | Inline centered text |
| Confirmations | Dialog overlay | Inline y/N prompt |
| Windows binary | Standalone .exe | Requires WSL/Git Bash |
| Scroll | Per-line smooth scroll | Page-based scroll |

## Architecture

```
nano-whale.sh (entry point)
    ├── config/defaults.sh     (configuration)
    ├── lib/utils.sh           (error handling, logging)
    ├── lib/config.sh          (platform detection)
    ├── lib/core.sh            (state management)
    ├── lib/tui.sh             (ANSI rendering)
    ├── lib/charts.sh          (sparkline charts)
    ├── lib/docker.sh          (Docker API)
    ├── lib/actions.sh         (container actions)
    ├── lib/stats.sh           (background stats)
    ├── lib/logging.sh         (log streaming)
    ├── lib/input.sh           (keyboard handler)
    ├── commands/exec.sh       (exec into container)
    ├── commands/logs.sh       (fullscreen logs)
    ├── commands/inspect.sh    (env/config/top tabs)
    └── commands/batch.sh      (multi-select helpers)
```

## Files Removed

- `nano_whale.js` — Original Node.js implementation
- `build.js` — Bun build/compile script
- `nano_whale.ico` — Windows icon (not needed)
- `install_win.sh` — PowerShell installer (replaced by INSTALL.sh)
- `.github/workflows/build-release.yml` — Binary build CI
