# nano-whale

Lightweight Docker TUI built **exclusively** with **Rust** (100% Rust-only project). Powered by **ratatui**, **tokio**, and **bollard**.

## Installation

Option 1: One-Line Install (Recommended)

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/Vriddhachalam/nano-whale/master/install_win.sh | iex
```

> **Note**
> For the best rendering experience on Windows, it is recommended to use **Git Bash** in **Windows Terminal** app.
> Avoid using `cmd` or `PowerShell` even in terminal app if possible to prevent rendering artifacts.

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/Vriddhachalam/nano-whale/master/install_linux_mac.sh | sh
```

## Requirements

- Rust 1.70+
- Docker daemon (`docker ps` must work)

## Build & run

```bash
cargo build --release
./target/release/nano-whale
```

WSL (recommended on Windows):

```bash
cd nano-whale-rs
cargo run --release
```

## Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `←` / `→` | Tabs (Logs, Stats, Env, Config, Top) |
| `↑` / `↓` | Navigate list |
| `Tab` | Cycle panel focus |
| `2`–`5` | Focus Containers / Images / Volumes / Networks |
| `s` | Start / stop container |
| `r` | Restart container |
| `d` | Delete selected resource |
| `m` | Mark / unmark |
| `F5` | Refresh hint (lists poll in background) |

## Performance

When more than **6** containers are present (default), stats are collected only for the **selected** running container. Parallel `docker stats` is capped (default 4). The UI redraws only when state changes or at ~60 FPS max (`NW_TICK_MS`).

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `NW_STATS_ALL_CONTAINER_MAX` | `6` | Above this count, stats poll only the selection |
| `NW_STATS_PARALLEL` | `4` | Max concurrent stats requests (1–8) |
| `NW_STATS_SELECTIVE_INTERVAL` | `1` | Seconds between selective stats polls |
| `NW_STATS_INTERVAL` | `2` | Seconds between full stats polls |
| `NW_CONTAINER_INTERVAL` | `3` | Seconds between `docker ps` polls |
| `NW_LOG_FLUSH_MS` | `120` | Throttle log UI updates |
| `NW_TICK_MS` | `16` | Min frame interval (~60 FPS cap) |
