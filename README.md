# 🐳 Nano Whale - Lightweight Docker TUI

[![Bun](https://img.shields.io/badge/Bun-1.0%2B-black)](https://bun.sh)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)](https://github.com/Vriddhachalam/nano-whale/releases)

<p align="center">
  <img src="img/nano_whale_w_bg.png" alt="Nano Whale logo">
</p>

**Nano Whale** is a blazingly fast, lightweight **Terminal User Interface (TUI)** for managing Docker containers, images, and volumes. Created as a compiled standalone binary, it requires **no external dependencies** (like Python or Node.js) to run on your machine.

---

## ✨ Features

- **🚀 Zero Dependencies**: Runs as a single binary executable. No Python/Pip required.
- **⚡ Blazingly Fast**: Built with Bun and Neo-Blessed for instant startup and low memory usage.
- **🖥️ Cross-Platform**: Native support for Windows (WSL2 integration), Linux, and macOS.
- **⌨️ Keyboard-Driven**: Efficient VIM-style navigation and shortcuts.
- **🛠️ Power Tools**:
    - **Instant logs**: Stream logs in full screen (`l`) or pane.
    - **Exec**: One-key shell access (`t`).
    - **Stats**: Real-time CPU/Mem usage graphs.
    - **Batch Actions**: Multi-select containers for bulk start/stop/remove.

---

![Gif](/img/app.gif)

## 📦 Installation


### Option 1: One-Line Install (Recommended)

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/Vriddhachalam/nano-whale/master/install_win.sh | iex
```

#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/Vriddhachalam/nano-whale/master/install_linux_mac.sh | sh
```

### Option 2: Run with Bun
If you have [Bun](https://bun.sh) installed:

```bash
# Clone repo
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale

# Install dependencies
bun init -y | bun install | bun install neo-blessed

# Run
bun run start
```

---

## 🚀 Usage

```bash
# If installed via binary
nano-whale

# If running from source
bun run start
```

---

## ⌨️ Keyboard Shortcuts

### Navigation
| Key | Action |
|-----|--------|
| `Tab` | Switch focus between lists |
| `↑/↓` | Navigate items |
| `PageUp/Down` | Scroll lists faster |
| `Home/End` | Jump to top/bottom |

### Tabs (Context Aware)
| Key | Action |
|-----|--------|
| `Logs` | View Logs tab |
| `Stats` | View Stats tab |
| `Env` | View Environment Variables |
| `Config` | View Inspection/Config |
| `Top` | View Top Processes |

### Actions
| Key | Action |
|-----|--------|
| `Enter` | **Inspect** / Expand details |
| `s` | **Start** container |
| `x` | **Stop** container |
| `r` | **Restart** container |
| `d` | **Delete** (Container/Image/Volume) |
| `l` | **Fullscreen Logs** (Live stream) |
| `ctrl + l` | **Fullscreen Logs** (Live stream in new window) |
| `t` | **Exec** (Enter shell) |
| `ctrl + t` | **Exec** (Enter shell in new window) |
| `a` | **Toggle Auto-scroll** (Logs) |
| `F5` | **Manual Refresh** (Reload all data) |
| `q` | **Quit** |

---

## 💻 Development

Built using **Bun** and **Neo-Blessed**.

```bash
# Setup
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale
bun install

# Dev Run
bun run dev

# Build Binaries
bun run build.js
```

---

## 🤝 Contributing
Contributions are welcome! Please submit a Pull Request.

## 📜 License
MIT License - see [LICENSE](LICENSE) for details.

---
**Made with ❤️ by Vriddhachalam S**
*Swim fast, stay light! 🐳*
