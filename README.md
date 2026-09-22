# 🐳 Nano Whale — Lightweight Docker TUI (Bash Edition)

[![Bash](https://img.shields.io/badge/Bash-4.3%2B-4EAA25?logo=gnu-bash&logoColor=white)](https://www.gnu.org/software/bash/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-blue)](https://github.com/Vriddhachalam/nano-whale)

<p align="center">
  <img src="img/nano_whale_w_bg.png" alt="Nano Whale logo">
</p>

**Nano Whale** is a lightweight **Terminal User Interface (TUI)** for managing Docker containers, images, volumes, and networks — written entirely in **Bash** with zero external runtime dependencies.

---

## ✨ Features

- **🚀 Zero Dependencies**: Pure Bash + ANSI escape codes. No Python, Node.js, or external TUI libraries required.
- **⚡ Instant Startup**: No compilation, no virtual environments. Just run the script.
- **🖥️ Cross-Platform**: Linux, macOS, and WSL (Windows Subsystem for Linux).
- **⌨️ Keyboard-Driven**: Efficient navigation and shortcuts.
- **🛠️ Power Tools**:
    - **Logs**: Live-streaming container logs + fullscreen mode
    - **Stats**: Real-time CPU/Memory sparkline charts
    - **Exec**: One-key shell access into containers
    - **Inspect**: Environment variables, configuration, top processes
    - **Batch Actions**: Multi-select for bulk start/stop/delete

---

## 📦 Installation

Nano Whale runs inside a Unix-like terminal. Before installing, make sure:

1. **Docker is installed and running.** Verify with `docker version`.
2. **Bash 4.3 or newer** is available. Verify with `bash --version`.
3. You are using a real interactive terminal (not a redirected pipe).

### Linux and macOS

```bash
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale
chmod +x INSTALL.sh
./INSTALL.sh
```

The installer:

- Copies the application to `~/.nano-whale`.
- Creates a `nano-whale` command in `~/.local/bin`.
- Makes the Bash scripts executable.
- Leaves the source checkout unchanged.

If `nano-whale` is not found after installation, add the install directory to
your current shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
nano-whale
```

To make that change permanent, add the same `export PATH=...` line to
`~/.bashrc` (Bash) or `~/.zshrc` (Zsh), then open a new terminal.

### Windows

Use **WSL2** or **Git Bash**. WSL2 is recommended because Docker Desktop
integrates with it most reliably.

**WSL2:**

```bash
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale
./INSTALL.sh
nano-whale
```

Make sure Docker Desktop is running and that WSL integration is enabled for
your distribution. Confirm that `docker version` can reach the Docker server
before starting Nano Whale.

**Git Bash:**

```bash
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale
./INSTALL.sh
```

If Git Bash cannot find Docker, add Docker Desktop's CLI directory to the
Windows `PATH`, restart Git Bash, and verify `docker version`.

### Run without installing

For a temporary run directly from the checkout:

```bash
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale
bash nano-whale.sh
```

### Verify the installation

```bash
command -v nano-whale
nano-whale --version
docker version
```

If Docker is not running, Nano Whale exits with a Docker connectivity error
instead of being able to display containers.

### Uninstall

The uninstaller removes the installed copy and launcher, but does not remove
Docker containers, images, volumes, or networks:

```bash
cd nano-whale
./uninstall.sh
```

---

## 🚀 Usage

```bash
# Launch the TUI
nano-whale

# Or run directly from source
./nano-whale.sh

# Show help
./nano-whale.sh --help

# Show version
./nano-whale.sh --version
```

---

## ⌨️ Keyboard Shortcuts

### Navigation
| Key | Action |
|-----|--------|
| `Tab` | Switch focus between lists |
| `↑/↓` | Navigate items |
| `PageUp/Down` | Scroll content faster |
| `Home/End` | Jump to top/bottom |
| `2/3/4/5` | Focus Containers/Images/Volumes/Networks |

### Tabs
| Key | Action |
|-----|--------|
| `←/→` | Cycle through tabs |
| Tabs | Logs, Stats, Env, Config, Top |

### Actions
| Key | Action |
|-----|--------|
| `s` | **Start/Stop** container |
| `r` | **Restart** container |
| `d` | **Delete** (Container/Image/Volume/Network) |
| `m` | **Mark/Unmark** item for batch operations |
| `Ctrl+A` | **Select/Deselect All** |
| `t` | **Exec** into container shell |
| `Ctrl+T` | **Exec** in new terminal window |
| `l` | **Fullscreen Logs** (live stream) |
| `Ctrl+D` | Return from fullscreen logs or the container shell |
| `Ctrl+L` | **Logs** in new terminal window |
| `a` | **Toggle Auto-scroll** (Logs) |
| `F5` | **Manual Refresh** |
| `q` | **Quit** |

---

## 📐 Architecture

```
nano-whale/
├── nano-whale.sh          # Main entry point & event loop
├── lib/
│   ├── core.sh            # State variables & constants
│   ├── config.sh          # Platform detection & Docker setup
│   ├── utils.sh           # Logging, error handling, cleanup
│   ├── tui.sh             # ANSI rendering engine
│   ├── input.sh           # Keyboard handler
│   ├── docker.sh          # Docker API layer
│   ├── actions.sh         # Container/image/volume actions
│   ├── stats.sh           # Background stats streaming
│   ├── logging.sh         # Log streaming
│   └── charts.sh          # Sparkline chart renderer
├── commands/
│   ├── exec.sh            # Shell exec (in-place & new window)
│   ├── logs.sh            # Fullscreen logs
│   ├── inspect.sh         # Env, Config, Top renderers
│   └── batch.sh           # Multi-select helpers
├── tests/
│   ├── run_tests.sh       # Test runner
│   ├── test_utils.sh      # Test framework
│   ├── test_docker.sh     # Docker parsing tests
│   ├── test_tui.sh        # TUI & state tests
│   ├── test_charts.sh     # Chart tests
│   └── test_input.sh      # CLI & input tests
├── config/
│   └── defaults.sh        # Default configuration
├── examples/
│   └── demo.sh            # Quick-start demo
├── INSTALL.sh             # Installer
├── uninstall.sh           # Uninstaller
├── REWRITE_PLAN.md        # Migration documentation
├── README.md              # This file
└── LICENSE                # MIT
```

---

## 🔧 Dependencies

### Required
| Tool | Purpose |
|------|---------|
| `bash` 4.3+ | Shell runtime |
| `docker` | Container management |

### Optional
| Tool | Purpose |
|------|---------|
| `jq` | Formatted container inspection (Config tab) |

All other utilities used (`tput`, `stty`, `timeout`, `hostname`, `uname`, `grep`, `sed`, `cat`, `tail`, `head`, `mktemp`, `kill`) are standard POSIX/GNU tools available on all Unix systems.

---

## 🧪 Testing

```bash
# Run all tests
bash tests/run_tests.sh

# Run individual test suite
bash tests/test_docker.sh
bash tests/test_tui.sh
bash tests/test_charts.sh
bash tests/test_input.sh

# Syntax check
bash -n nano-whale.sh
```

---

## 💻 Development

```bash
# Clone
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale

# Run directly
./nano-whale.sh

# Run tests
bash tests/run_tests.sh
```

No build step required — it's just Bash.

---

## 🤝 Contributing
Contributions are welcome! Please submit a Pull Request.

## 📜 License
MIT License — see [LICENSE](LICENSE) for details.

---
**Made with ❤️ by Vriddhachalam S**
*Swim fast, stay light! 🐳*
