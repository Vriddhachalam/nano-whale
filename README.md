# 🐳 Nano Whale - Lightweight Docker TUI
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Textual](https://img.shields.io/badge/built%20with-Textual-cyan.svg)](https://textual.textualize.io/)

<p align="center">
  <img src="./img/nano_whale_w_bg.png" alt="Nano Whale logo" >
</p>

> ⚠️ **DEPRECATION NOTICE**: The original Tkinter GUI version of Nano Whale has been deprecated. This repository now contains the new and improved **Terminal User Interface (TUI)** version built with Textual. For the legacy version, see the `legacy-tkinter` branch.

Meet **Nano Whale TUI**! A blazingly fast, lightweight **Terminal User Interface** for managing Docker containers, images, and volumes. Built with [Textual](https://textual.textualize.io/), Nano Whale provides an elegant, keyboard-driven interface for Docker management without the overhead of Docker Desktop.

---

## ✨ Features

- **Blazingly Fast & Lightweight**: Minimal resource footprint, native WSL2 integration.
- **Efficient Management**: Keyboard-driven TUI for containers, images, and volumes.
- **Detailed Inspection**: Quickly view container info, environment, ports, volumes, and networks.
- **Batch Operations**: Multi-select for streamlined management (start, stop, delete).
- **Cross-Platform**: Works seamlessly on Windows (WSL), Linux, and macOS.

---

## 🖼️ Screenshots

### Main Interface
<p align="center">
  <img src="./img/main.png" alt="Nano Whale TUI - Main Interface" width="900">
</p>

### Multi-Select Mode
<p align="center">
  <img src="./img/multi_select.png" alt="Nano Whale TUI - Multi-Select" width="900">
</p>

### Commands Panel
<p align="center">
  <img src="./img/commands_panel.png" alt="Nano Whale TUI - Commands Panel" width="900">
</p>

---

## 📦 Installation

### Via pip (Recommended)

```bash
pip install nano-whale
```

### Via pipx (Isolated)

```bash
pipx install nano-whale
```

## From GitHub Releases

### Via Windows Executable
For Windows users who prefer a standalone executable without Python or `pip` installation, you can [download](https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-windows-latest-manual.exe) the latest release directly from GitHub or follow the below PowerShell script for shell command.

```powershell
# 1. Download the executable
Invoke-WebRequest -Uri "https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-windows-latest-manual.exe" -OutFile "nano-whale-windows-latest-manual.exe"

# 2. Move to C:\Tools and rename
New-Item -Path "C:\Tools" -ItemType Directory -Force
Move-Item .\nano-whale-windows-latest-manual.exe C:\Tools\nano-whale.exe

# 3. Add C:\Tools to PATH
[System.Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Tools", [System.EnvironmentVariableTarget]::Machine)

# 4. Test installation (requires terminal restart if PATH was updated)
nano-whale
```
---

### Via Linux Executable
For Linux users who prefer a standalone executable, download the latest release from GitHub using this bash script:

```bash
# 1. Download the executable
curl -L -o nano-whale-ubuntu-latest https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-ubuntu-latest

# 2. Make it executable
chmod +x nano-whale-ubuntu-latest

# 3. Move to /usr/local/bin with a clean name
sudo mv nano-whale-ubuntu-latest /usr/local/bin/nano-whale

# 4. Test installation
nano-whale
```

---

## 🚀 Usage

Simply run:

```bash
nano-whale
```

Or run directly:

```bash
python nano_whale/main.py
```

---

## ⌨️ Keyboard Shortcuts

### Table Navigation
| Key | Action |
|-----|--------|
| `C` | Switch to **Containers** table |
| `I` | Switch to **Images** table |
| `V` | Switch to **Volumes** table |
| `↑/↓` | Navigate rows |
| `Page Up/Down` | Fast scroll |
| `Home/End` | Jump to first/last row |
| **Mouse Click** | Click anywhere on table section to switch |

### Detail Panel Tabs
| Key | Action |
|-----|--------|
| `1` | **Info** tab - Container details |
| `2` | **Env** tab - Environment variables |
| `3` | **Ports** tab - Port mappings |
| `4` | **Volumes** tab - Volume mounts |
| `5` | **Networks** tab - Network configuration |

### Container Operations
| Key | Action |
|-----|--------|
| `S` | **Start** container(s) |
| `X` | **Stop** container(s) |
| `R` | **Restart** container(s) |
| `D` | **Delete** selected item(s) |

### Logs & Terminal
| Key | Action |
|-----|--------|
| `L` | View **Logs** in-shell (suspends TUI) |
| `Ctrl+L` | View **Logs** in new terminal window |
| `T` | Launch **Terminal** in-shell (exec) |
| `Ctrl+T` | Launch **Terminal** in new window |

### Multi-Select & Batch Operations
| Key | Action |
|-----|--------|
| `M` | **Mark/Unmark** current item |
| *(then)* `S/X/R/D` | Perform action on all marked items |

### Utilities
| Key | Action |
|-----|--------|
| `A` | **Refresh** all tables |
| `G` | Toggle **Stats** display in container list |
| `P` | **Prune** menu (press twice to confirm) |
| `Q` | **Quit** application |

---

### Viewing Logs / Exec into containers

**In-Shell (suspends TUI, Useful for non GUI servers):**
1. Select a running container
2. Press `L` or `T` Logs stream
3. Press `Ctrl+C` or `Ctrl+D` to return to TUI

<p align="center">
  <img src="./img/in_shell_logs.png" alt="Nano Whale TUI - In-Shell Logs" width="900">
</p>

<p align="center">
  <img src="./img/in_shell_exec_terminal.png" alt="Nano Whale TUI - In-Shell Exec Terminal" width="900">
</p>


**In New Window (TUI remains active):**
1. Select a running container
2. Press `Ctrl+L` or `Ctrl+T`

<p align="center">
  <img src="./img/new_shell_logs.png" alt="Nano Whale TUI - New Shell Logs" width="900">
</p>

<p align="center">
  <img src="./img/new_shell_terminal.png" alt="Nano Whale TUI - New Shell Terminal" width="900">
</p>


### Cleaning Up System

1. Press `P` - shows warning notification
2. Press `P` again within 5 seconds to confirm
3. Executes `docker system prune -a -f`
4. Removes all unused containers, images, and volumes


## 💻 Dev Zone: Running from Source

### Development Setup

```bash
# Clone the repository
git clone https://github.com/Vriddhachalam/nano-whale.git
cd nano-whale

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows
# source .venv/bin/activate  # On Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .

# Run from source
python nano_whale/main.py
```

### 📦 Building Portable Executable with Nuitka

**Build Command:**

```bash
python -m nuitka --standalone --onefile --output-filename=nano-whale nano_whale/main.py
```

**Build Options Explained:**
| Option | Description |
|--------|-------------|
| `--standalone` | Include all dependencies |
| `--onefile` | Package everything into a single executable |
| `--windows-console-mode=force` | Keep console window for TUI |
| `--output-filename` | Name of the output executable |

The portable executable can be distributed and run on any compatible system without Python installation!

---

## 🐛 Troubleshooting

### "wsl command not found" (Windows)

```bash
wsl --install
# Restart computer after installation
```

### "Cannot connect to Docker daemon"

**Linux/macOS:**
```bash
sudo systemctl start docker
# or
sudo service docker start
```

**Windows WSL:**
```bash
wsl sudo service docker start
```

### "Permission denied"

```bash
sudo usermod -aG docker $USER
# Then log out and back in
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 📚 Migration from Legacy GUI Version

If you're upgrading from the old Tkinter GUI version:

1. **No more .exe**: The new TUI version runs directly with Python
2. **Keyboard-driven**: Learn the keyboard shortcuts for faster workflow
3. **Better performance**: Even lighter resource usage than before
4. **SSH compatible**: Now works over remote connections
5. **New features**: Split-pane interface, container inspection tabs, multi-select

The legacy Tkinter version can still be found in the `legacy-tkinter` branch, but it will no longer receive updates.

### Legacy Version Screenshots (Deprecated)

<p align="center">
  <img src="./img/face.png" alt="Legacy GUI - Main" width="738">
</p>
<p align="center">
  <img src="./img/images.png" alt="Legacy GUI - Images" width="738">
</p>
<p align="center">
  <img src="./img/logs.png" alt="Legacy GUI - Logs" width="738">
</p>
<p align="center">
  <img src="./img/terminal.png" alt="Legacy GUI - Terminal" width="738">
</p>

---

## ⭐ Star History

If you find Nano Whale useful, please consider giving it a star on GitHub!

---

**Made with ❤️ by Vriddhachalam S**

*Swim fast, stay light! 🐳*
