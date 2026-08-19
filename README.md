# 🐳 Nano Whale - Lightweight Docker TUI

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)](https://github.com/Karthikeyan-070204/nano-whale/releases)

<p align="center">
  <img src="img/nano_whale_w_bg.png" alt="Nano Whale logo">
</p>

**Nano Whale** is a blazingly fast, lightweight **Terminal User Interface (TUI)** for managing Docker containers, images, and volumes. Completely rewritten from the ground up in native **C++**, it requires **no external dependencies** (like Python, Node.js, or Bun) to run on your machine.

---

## ✨ Features

- **🚀 Zero Dependencies**: Runs as a single binary executable. No runtimes required.
- **⚡ Blazingly Fast**: Built with modern C++ and FTXUI for instant startup and virtually zero memory usage.
- **🖥️ Cross-Platform**: Native support for Windows (WSL2 integration), Linux, and macOS.
- **⌨️ Keyboard-Driven**: Efficient VIM-style navigation and shortcuts.
- **🛠️ Power Tools**:
    - **Dashboard**: Quick overview of running and stopped containers.
    - **Deep Inspector**: Real-time CPU, Mem, and Network usage graphs.
    - **System Prune**: Safe and easy bulk cleanup for dangling images and unused volumes.
    - **File Explorer**: Browse your container's filesystem and download files straight to the host.
    - **Docker Compose**: Full compose integration with live log streaming.
    - **Instant Shell**: Drop into an interactive shell (`/bin/sh`) instantly.

---

## 📦 Installation

### Option 1: One-Line Install (Recommended)

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/Karthikeyan-070204/nano-whale/master/install_win.ps1 | iex
```

> [!NOTE]
> For the best rendering experience on Windows, it is recommended to use **Git Bash** in **Windows Terminal** app. Avoid using `cmd` or `PowerShell` even in the terminal app if possible to prevent rendering artifacts.

#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/Karthikeyan-070204/nano-whale/master/install_linux_mac.sh | sh
```

### Option 2: Build from Source

If you have `CMake` and a modern C++ compiler installed:

```bash
# Clone repo
git clone https://github.com/Karthikeyan-070204/nano-whale.git
cd nano-whale

# Configure and Build
cmake -B build
cmake --build build

# Run
./build/nano-whale
```

---

## 🚀 Usage

Ensure your Docker daemon is running, then run:

```bash
# If running the downloaded binary
./nano-whale

# If running from source build
./build/nano-whale
```

---

## ⌨️ Keyboard Shortcuts

### Navigation
| Key | Action |
|-----|--------|
| `Tab` / `Left/Right` | Switch between Top Tabs |
| `↑/↓` | Navigate lists and menus |
| `PageUp/Down` | Scroll lists faster |

### Actions
| Key | Action |
|-----|--------|
| `Enter` | **Inspect** / Expand details |
| `s` | **Start** container |
| `x` | **Stop** container |
| `r` | **Restart** container |
| `d` | **Delete** (Container/Image/Volume) |
| `l` | **Fullscreen Logs** (Live stream) |
| `t` | **Exec** (Enter shell inside container) |
| `F5` | **Manual Refresh** (Reload all data) |
| `q` or `Esc` | **Go Back** / **Quit** |

---

## 🤝 Contributing
Contributions are welcome! Please submit a Pull Request.

## 📜 License
MIT License - see [LICENSE](LICENSE) for details.

---
**Made with ❤️ by Vriddhachalam S & Karthikeyan**
*Swim fast, stay light! 🐳*
