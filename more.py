import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
from ctypes import c_int, c_long, c_void_p, c_wchar_p, windll
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import requests
import tkcalendar as tkc
from dotenv import load_dotenv

# Make the application DPI aware
try:
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

CREATE_NO_WINDOW = 0x08000000
DOCKER_CMD_PREFIX = ["wsl", "docker"]


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class UniversalDockerManager:
    """
    Combined Docker Manager with deployment automation and resource management.
    Includes WSL/Docker prerequisite checking and installation.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Universal Docker Manager")
        self.root.geometry("1200x900")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Set icon
        try:
            icon_path = resource_path("nano_whale.ico")
            self.root.iconbitmap(icon_path)
        except:
            pass

        # Load environment variables
        self.env_path = self.get_env_path()
        load_dotenv(self.env_path)

        # Configuration
        self.config_file = self.get_config_path()
        self.config = self.load_config()

        # Git/Deployment settings
        self.repo_url = os.getenv("GIT_REPO_URL", "")
        self.git_token = os.getenv("GIT_TOKEN", "")
        self.default_branch = os.getenv("DEFAULT_BRANCH", "main")
        self.repo_name = os.getenv("REPO_NAME", "repository")
        self.default_branch = self.config.get("default_branch", "main")
        self.clone_dir = os.path.join(os.getcwd(), self.repo_name)

        # Command pipelines
        self.pre_deploy_commands = self.config.get("pre_deploy_commands", [])
        self.docker_commands = self.config.get(
            "docker_commands", ["docker compose up -d --build"]
        )
        self.post_deploy_commands = self.config.get("post_deploy_commands", [])

        # Docker monitoring
        self.active_log_threads = []
        self.prerequisites_checked = False
        self.prerequisites_ok = False

        # Detected dependencies
        self.detected_deps = {}
        self.local_deps_needed = {}
        self.installed_versions = {}

        # Setup UI
        self.setup_ui()

        # Start prerequisite check
        self._start_prereq_check()

    def _refresh_env_vars(self):
        """
        Attempts to force-refresh the process environment by reading the system registry
        and broadcasting a WM_SETTINGCHANGE message (Windows-specific fix).
        """
        self.log("Attempting to refresh environment variables...", "INFO")
        try:
            # 1. Read system PATH from Registry
            reg_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            )
            path_tuple = winreg.QueryValueEx(reg_key, "Path")
            system_path = path_tuple[0]
            winreg.CloseKey(reg_key)

            # 2. Update Python's os.environ
            os.environ["PATH"] = system_path

            # 3. Broadcast WM_SETTINGCHANGE message to all windows
            SMTO_ABORTIFHUNG = 0x0002
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A

            # Define function signature
            SendMessageTimeout = windll.user32.SendMessageTimeoutW
            SendMessageTimeout.argtypes = [
                c_long,
                c_long,
                c_long,
                c_wchar_p,
                c_long,
                c_long,
                c_void_p,
            ]

            # Send the broadcast message
            result = SendMessageTimeout(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                c_int(0),
                c_wchar_p("Environment"),
                SMTO_ABORTIFHUNG,
                5000,
                c_void_p(None),
            )

            if result != 0:
                self.log("✓ Environment refresh complete.", "INFO")
            else:
                self.log("⚠ Environment broadcast failed or timed out.", "WARNING")

        except Exception as e:
            self.log(f"Failed to refresh environment variables: {e}", "ERROR")

        # Add a small delay for the system to process
        time.sleep(1)

    def get_env_path(self):
        """Get path to .env file"""
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), ".env")
        else:
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    def get_config_path(self):
        """Get path to config file"""
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), "deployer_config.json")
        else:
            return os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "deployer_config.json"
            )

    def load_config(self):
        """Load configuration from JSON file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_config(self):
        """Save configuration to JSON file"""
        config = {
            "repo_url": self.repo_url_entry.get(),
            "git_token": self.token_entry.get(),
            "default_branch": self.branch_var.get(),
            "repo_name": self.repo_name_entry.get(),
            "pre_deploy_commands": self.get_commands_from_text(self.pre_deploy_text),
            "docker_commands": self.get_commands_from_text(self.docker_text),
            "post_deploy_commands": self.get_commands_from_text(self.post_deploy_text),
        }
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
        self.log("✓ Configuration saved", "SUCCESS")

    def get_commands_from_text(self, text_widget):
        """Extract non-empty lines from text widget"""
        content = text_widget.get("1.0", tk.END).strip()
        return [
            line.strip()
            for line in content.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

    def setup_ui(self):
        """Create main UI with all tabs"""
        # Status panel at top
        self.create_status_panel()

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 1: Configuration
        config_tab = ttk.Frame(self.notebook)
        self.notebook.add(config_tab, text="Configuration")
        self.setup_config_tab(config_tab)

        # Tab 2: Commands
        commands_tab = ttk.Frame(self.notebook)
        self.notebook.add(commands_tab, text="Command Pipeline")
        self.setup_commands_tab(commands_tab)

        # Tab 3: Deploy & Monitor
        deploy_tab = ttk.Frame(self.notebook)
        self.notebook.add(deploy_tab, text="Deploy & Monitor")
        self.setup_deploy_tab(deploy_tab)

        # Tab 4: Containers
        self.create_container_tab()

        # Tab 5: Images
        self.create_image_tab()

        # Tab 6: Volumes
        self.create_volume_tab()

    def create_status_panel(self):
        """Create the status/log panel at the top"""
        status_frame = ttk.LabelFrame(self.root, text="System Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        self.status_text = scrolledtext.ScrolledText(
            status_frame,
            wrap=tk.WORD,
            height=6,
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 9),
        )
        self.status_text.pack(fill=tk.BOTH, expand=True)

        # Button frame
        button_frame = ttk.Frame(status_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))

        self.retry_check_btn = ttk.Button(
            button_frame,
            text="Retry Prerequisites Check",
            command=self._start_prereq_check,
            state=tk.DISABLED,
        )
        self.retry_check_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(
            side=tk.LEFT, padx=5
        )

    def setup_config_tab(self, parent):
        """Setup configuration tab"""
        # Repository Configuration Frame
        repo_frame = ttk.LabelFrame(
            parent, text="Repository Configuration", padding="10"
        )
        repo_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(repo_frame, text="Repository URL:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.repo_url_entry = ttk.Entry(repo_frame, width=60)
        self.repo_url_entry.insert(0, self.repo_url)
        self.repo_url_entry.grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5
        )

        ttk.Label(repo_frame, text="Git Token (PAT):").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.token_entry = ttk.Entry(repo_frame, width=60, show="*")
        self.token_entry.insert(0, self.git_token)
        self.token_entry.grid(
            row=1, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5
        )

        ttk.Label(repo_frame, text="Local Folder Name:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.repo_name_entry = ttk.Entry(repo_frame, width=30)
        self.repo_name_entry.insert(0, self.repo_name)
        self.repo_name_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Label(repo_frame, text="Branch:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.branch_var = tk.StringVar(value=self.default_branch)
        self.branch_combo = ttk.Combobox(
            repo_frame, textvariable=self.branch_var, width=20
        )
        self.branch_combo.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Button(
            repo_frame, text="Fetch Branches", command=self.refresh_branches
        ).grid(row=3, column=2, sticky=tk.W, padx=5)
        ttk.Button(
            repo_frame, text="Analyze Repository", command=self.analyze_repo
        ).grid(row=4, column=1, sticky=tk.W, pady=10, padx=5)

        repo_frame.columnconfigure(1, weight=1)

        # Detected Dependencies Frame
        deps_frame = ttk.LabelFrame(parent, text="Detected Dependencies", padding="10")
        deps_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.deps_text = scrolledtext.ScrolledText(deps_frame, wrap=tk.WORD, height=10)
        self.deps_text.pack(fill=tk.BOTH, expand=True)

        # Local Installation Requirements Frame
        local_deps_frame = ttk.LabelFrame(
            parent, text="Local Installation Requirements", padding="10"
        )
        local_deps_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.local_deps_text = scrolledtext.ScrolledText(
            local_deps_frame, wrap=tk.WORD, height=8
        )
        self.local_deps_text.pack(fill=tk.BOTH, expand=True)

        # Install button
        install_frame = ttk.Frame(local_deps_frame)
        install_frame.pack(fill=tk.X, pady=5)

        self.install_local_deps_btn = ttk.Button(
            install_frame,
            text="🔧 Install/Update Local Dependencies",
            command=self.install_local_dependencies,
            state=tk.DISABLED,
        )
        self.install_local_deps_btn.pack(side=tk.LEFT, padx=5)

        ttk.Label(
            install_frame,
            text="(Installs Node.js, Python, Go, Ruby via Chocolatey/Scoop)",
            foreground="gray",
        ).pack(side=tk.LEFT, padx=5)

        # Save Configuration Button
        ttk.Button(parent, text="Save Configuration", command=self.save_config).pack(
            pady=10
        )

    def setup_commands_tab(self, parent):
        """Setup command pipeline tab"""
        # Instructions
        info_label = ttk.Label(
            parent,
            text="Define your deployment pipeline. Use 'cd /path' to change directory. Lines starting with # are comments.",
            wraplength=1100,
        )
        info_label.pack(padx=10, pady=5)

        # Pre-Deploy Commands
        pre_frame = ttk.LabelFrame(
            parent, text="Pre-Deploy Commands (runs before Docker)", padding="10"
        )
        pre_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.pre_deploy_text = scrolledtext.ScrolledText(
            pre_frame, wrap=tk.WORD, height=6
        )
        self.pre_deploy_text.pack(fill=tk.BOTH, expand=True)
        if self.pre_deploy_commands:
            self.pre_deploy_text.insert("1.0", "\n".join(self.pre_deploy_commands))
        else:
            self.pre_deploy_text.insert(
                "1.0",
                "# Example:\n# cd /backend && npm install\n# python scripts/setup.py",
            )

        # Docker Commands
        docker_frame = ttk.LabelFrame(parent, text="Docker Commands", padding="10")
        docker_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.docker_text = scrolledtext.ScrolledText(
            docker_frame, wrap=tk.WORD, height=4
        )
        self.docker_text.pack(fill=tk.BOTH, expand=True)
        if self.docker_commands:
            self.docker_text.insert("1.0", "\n".join(self.docker_commands))
        else:
            self.docker_text.insert("1.0", "docker compose up -d --build")

        # Post-Deploy Commands
        post_frame = ttk.LabelFrame(
            parent, text="Post-Deploy Commands (runs after Docker starts)", padding="10"
        )
        post_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.post_deploy_text = scrolledtext.ScrolledText(
            post_frame, wrap=tk.WORD, height=6
        )
        self.post_deploy_text.pack(fill=tk.BOTH, expand=True)
        if self.post_deploy_commands:
            self.post_deploy_text.insert("1.0", "\n".join(self.post_deploy_commands))
        else:
            self.post_deploy_text.insert(
                "1.0",
                "# Example:\n# docker exec app python manage.py migrate\n# cd /web && npm run dev",
            )

    def setup_deploy_tab(self, parent):
        """Setup deployment tab"""
        # Action Buttons Frame
        button_frame = ttk.Frame(parent, padding="10")
        button_frame.pack(fill=tk.X)

        self.deploy_btn = ttk.Button(
            button_frame,
            text="🚀 Deploy/Update",
            command=self.deploy,
            state=tk.DISABLED,
        )
        self.deploy_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(
            button_frame, text="⏹ Stop Services", command=self.stop_services
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame, text="🧹 Clean Clone Directory", command=self.clean_clone_dir
        ).pack(side=tk.LEFT, padx=5)

        # Deployment Log Frame
        log_frame = ttk.LabelFrame(parent, text="Deployment Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.deploy_log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, height=25
        )
        self.deploy_log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message, level="INFO"):
        """Thread-safe logging to status window"""

        def update_log():
            timestamp = time.strftime("%H:%M:%S")
            self.status_text.insert(tk.END, f"[{timestamp}] [{level}] {message}\n")
            self.status_text.see(tk.END)
            self.status_text.update_idletasks()

        if hasattr(self, "status_text"):
            self.root.after(0, update_log)

    def deploy_log(self, message, level="INFO"):
        """Thread-safe logging to deployment log"""

        def update_log():
            timestamp = time.strftime("%H:%M:%S")
            self.deploy_log_text.insert(tk.END, f"[{timestamp}] [{level}] {message}\n")
            self.deploy_log_text.see(tk.END)

        if hasattr(self, "deploy_log_text"):
            self.root.after(0, update_log)

    def clear_log(self):
        """Clear the status log"""
        self.status_text.delete("1.0", tk.END)

    def on_close(self):
        """Clean up before closing"""
        for thread in self.active_log_threads:
            if thread.is_alive() and thread.log_process:
                thread.log_process.terminate()
        self.root.destroy()
        sys.exit(0)

    # === PREREQUISITE CHECKING ===

    def _start_prereq_check(self):
        """Start prerequisite check in background thread"""
        self.log("Starting prerequisite check...", "INFO")
        self.retry_check_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._check_prerequisites_threaded, daemon=True).start()

    def _check_prerequisites_threaded(self):
        """Run prerequisite checks in a separate thread"""
        all_ok = self.check_prerequisites()

        self.prerequisites_checked = True
        self.prerequisites_ok = all_ok

        if all_ok:
            self.log("✓ All prerequisites met! Docker Manager is ready.", "SUCCESS")
            self.root.after(0, lambda: self.enable_docker_operations())
            self.root.after(0, self.refresh_all)
        else:
            self.log(
                "✗ Prerequisites not met. Please follow instructions above.", "ERROR"
            )
            self.root.after(0, lambda: self.disable_docker_operations())

        self.root.after(0, lambda: self.retry_check_btn.config(state=tk.NORMAL))

    def check_prerequisites(self):
        """Check if WSL, Docker Engine, and Git are installed"""
        self.log("Checking prerequisites...")
        all_ok = True

        # Check Git
        success, stdout, _ = self.run_command("git --version", shell=True)
        if success:
            self.log(f"✓ Git: {stdout.strip()}")
        else:
            self.log("✗ Git not installed", "ERROR")
            all_ok = False

        # Check WSL 2
        self.log("Checking WSL 2 installation...", "INFO")
        wsl_ok = self._check_wsl()

        if not wsl_ok:
            self.log("✗ WSL 2 is not installed or not working", "ERROR")
            self.log("Attempting to install WSL 2...", "INSTALL")
            if self._install_wsl():
                all_ok = False
                return all_ok
            else:
                all_ok = False
        else:
            self.log("✓ WSL 2 is installed and working", "SUCCESS")

        # Check Docker Engine in WSL
        if wsl_ok:
            self.log("Checking Docker Engine in WSL...", "INFO")
            docker_ok = self._check_docker_engine()

            if not docker_ok:
                self.log("✗ Docker Engine is not installed in WSL", "ERROR")
                self.log("Attempting to install Docker Engine...", "INSTALL")
                if not self._install_docker_engine():
                    all_ok = False
            else:
                self.log("✓ Docker Engine is installed and working in WSL", "SUCCESS")

                if self._check_docker_daemon():
                    self.log("✓ Docker daemon is running", "SUCCESS")
                else:
                    self.log(
                        "⚠ Docker daemon is not running. Attempting to start...",
                        "WARNING",
                    )
                    self._start_docker_daemon()

        return all_ok

    def _check_wsl(self):
        """Check if WSL 2 is installed"""
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                ["wsl", "--status"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=flags,
            )
            return result.returncode == 0
        except:
            return False

    def _check_docker_engine(self):
        """Check if Docker CLI is available in WSL"""
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                ["wsl", "docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=flags,
            )
            return result.returncode == 0
        except:
            return False

    def _check_docker_daemon(self):
        """Check if Docker daemon is running"""
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                DOCKER_CMD_PREFIX + ["ps"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=flags,
            )
            return result.returncode == 0
        except:
            return False

    def _start_docker_daemon(self):
        """Attempt to start Docker daemon"""
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            subprocess.run(
                ["wsl", "sudo", "service", "docker", "start"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=flags,
            )
            time.sleep(2)
            if self._check_docker_daemon():
                self.log("✓ Docker daemon started successfully", "SUCCESS")
            else:
                self.log("⚠ Failed to start Docker daemon automatically", "WARNING")
        except Exception as e:
            self.log(f"Failed to start Docker daemon: {e}", "ERROR")

    def _install_wsl(self):
        """Install WSL 2"""
        self.log(
            "Executing WSL installation (requires Administrator privileges)...",
            "INSTALL",
        )

        try:
            result = subprocess.run(
                ["wsl", "--install"],
                capture_output=True,
                text=True,
                timeout=1200,
                shell=True,
            )

            if result.returncode == 0:
                self.log("✓ WSL install command executed successfully", "SUCCESS")
                self.log("=" * 60, "FATAL")
                self.log("SYSTEM REBOOT REQUIRED!", "FATAL")
                self.log("=" * 60, "FATAL")
                self.log(
                    "Please REBOOT YOUR COMPUTER to complete WSL installation.", "FATAL"
                )
                self.log("After rebooting, run this application again.", "FATAL")

                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "REBOOT REQUIRED",
                        "WSL installation requires a system reboot.\n\n"
                        "Please REBOOT YOUR COMPUTER NOW, then run this application again.",
                    ),
                )
                return True
            else:
                self.log(f"WSL installation failed: {result.stderr}", "ERROR")
                self.log(
                    "Please ensure this application is run as Administrator.", "ERROR"
                )
                return False

        except Exception as e:
            self.log(f"WSL installation error: {e}", "ERROR")
            return False

    def _install_docker_engine(self):
        """Install Docker Engine in WSL using automated script"""
        self.log("Launching Docker Engine installation in new terminal...", "INSTALL")

        DOCKER_INSTALL_SCRIPT = (
            "echo '=== Docker Engine Installation (Password Required) ===';"
            "sudo apt update -y && sudo apt upgrade -y;"
            "sudo apt install -y ca-certificates curl gnupg lsb-release;"
            "sudo install -m 0755 -d /etc/apt/keyrings;"
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg;"
            "sudo chmod a+r /etc/apt/keyrings/docker.gpg;"
            "echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu jammy stable' | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null;"
            "sudo apt update -y --allow-unauthenticated;"
            "sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin;"
            "sudo service docker start;"
            "sudo usermod -aG docker $USER || echo 'User mod command completed';"
            "echo '=== Installation Complete ===';"
            "echo 'IMPORTANT: Close this window and click Retry Prerequisites Check';"
            "echo 'Press Enter to close...';"
            "read;"
        )

        escaped_script = DOCKER_INSTALL_SCRIPT.replace('"', '\\"')
        command = f'start "" cmd /K wsl sh -c "{escaped_script}"'

        try:
            subprocess.Popen(command, shell=True)

            self.log("✓ Installation terminal launched", "SUCCESS")
            self.log("=" * 60, "WARNING")
            self.log("ACTION REQUIRED:", "WARNING")
            self.log("1. Enter your WSL password in the new terminal window", "WARNING")
            self.log("2. Wait for installation to complete", "WARNING")
            self.log("3. Press Enter in that terminal to close it", "WARNING")
            self.log("4. Click 'Retry Prerequisites Check' button", "WARNING")
            self.log("=" * 60, "WARNING")

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Manual Step Required",
                    "A terminal window has opened for Docker Engine installation.\n\n"
                    "Steps:\n"
                    "1. Enter your WSL password when prompted by sudo\n"
                    "2. Wait for installation to complete\n"
                    "3. Press Enter to close the terminal\n"
                    "4. Click 'Retry Prerequisites Check' in this window",
                ),
            )

            return False

        except Exception as e:
            self.log(f"Failed to launch installation: {e}", "ERROR")
            return False

    def enable_docker_operations(self):
        """Enable all Docker operation buttons"""
        self.deploy_btn.config(state=tk.NORMAL)

    def disable_docker_operations(self):
        """Disable Docker operation buttons when prerequisites aren't met"""
        self.deploy_btn.config(state=tk.DISABLED)

    # === COMMAND EXECUTION ===

    def _execute_command(
        self,
        command_parts,
        success_message="Command executed successfully.",
        error_message="Error executing command.",
    ):
        """Execute a Docker command using WSL prefix"""
        if not self.prerequisites_ok:
            messagebox.showerror(
                "Prerequisites Not Met",
                "WSL and Docker Engine must be installed first.\n"
                "Please complete the prerequisite checks.",
            )
            return False, ""

        full_command = DOCKER_CMD_PREFIX + command_parts
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                timeout=60,
                creationflags=flags,
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            msg = f"{error_message}\nSTDOUT: {e.stdout.strip()}\nSTDERR: {e.stderr.strip()}"
            messagebox.showerror("Docker Error", msg)
            return False, e.stderr
        except FileNotFoundError:
            msg = "Error: 'wsl' command not found. WSL may not be installed properly."
            messagebox.showerror("Execution Error", msg)
            return False, msg
        except subprocess.TimeoutExpired:
            msg = "Command timed out. Docker daemon may not be responding."
            messagebox.showerror("Timeout Error", msg)
            return False, msg
        except Exception as e:
            msg = f"An unexpected error occurred: {e}"
            messagebox.showerror("Unexpected Error", msg)
            return False, msg

    def run_command(self, command, cwd=None, shell=True, timeout=300):
        """Run shell command and return output"""
        try:
            if command.strip().startswith("cd "):
                return True, "", ""

            result = subprocess.run(
                command,
                cwd=cwd,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    def refresh_all(self):
        """Refreshes data in all tabs"""
        if self.prerequisites_ok:
            self.refresh_containers()
            self.refresh_images()
            self.refresh_volumes()

    def _get_selected_id(self, tree):
        """Get selected item ID from treeview"""
        selected_item = tree.focus()
        if not selected_item:
            messagebox.showwarning(
                "Selection Required", "Please select a resource first."
            )
            return None
        return selected_item

    # === CONTAINER TAB ===

    def create_container_tab(self):
        container_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(container_frame, text="Containers")

        columns = ("ID", "Name", "Image", "Status")
        self.containers_tree = ttk.Treeview(
            container_frame, columns=columns, show="headings"
        )
        self.containers_tree.pack(fill="both", expand=True)

        for col in columns:
            self.containers_tree.heading(col, text=col)
            self.containers_tree.column(col, anchor=tk.W, width=100)

        self.containers_tree.column("ID", width=100)
        self.containers_tree.column("Name", width=200)
        self.containers_tree.column("Image", width=200)
        self.containers_tree.column("Status", width=150)

        vsb = ttk.Scrollbar(
            container_frame, orient="vertical", command=self.containers_tree.yview
        )
        vsb.pack(side="right", fill="y")
        self.containers_tree.configure(yscrollcommand=vsb.set)
        self.containers_tree.bind(
            "<Control-a>", lambda e: self.select_all(self.containers_tree)
        )

        button_frame = ttk.Frame(container_frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="Refresh", command=self.refresh_containers).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            button_frame, text="Start", command=lambda: self.manage_container("start")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame, text="Stop", command=lambda: self.manage_container("stop")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="Restart",
            command=lambda: self.manage_container("restart"),
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="View Logs", command=self.show_logs).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Terminal", command=self.exec_terminal).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            button_frame, text="Prune Exited", command=self.prune_containers
        ).pack(side=tk.LEFT, padx=5)

    def refresh_containers(self):
        """Fetch and display containers"""
        success, output = self._execute_command(
            ["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"],
            success_message="Containers refreshed.",
        )

        for item in self.containers_tree.get_children():
            self.containers_tree.delete(item)

        if success and output:
            for line in output.strip().split("\n"):
                if line:
                    try:
                        cid, name, image, status = line.split("\t", 3)
                        display_id = cid[:12]
                        self.containers_tree.insert(
                            "",
                            tk.END,
                            values=(display_id, name, image, status),
                            iid=cid,
                        )
                    except ValueError:
                        print(f"Skipping malformed container output line: {line}")

    def manage_container(self, action):
        """Perform start, stop, or restart on selected containers"""
        selected_containers = self.containers_tree.selection()

        if not selected_containers:
            messagebox.showwarning(
                "Selection Required", "Please select container(s) first."
            )
            return

        if action == "stop":
            flags = CREATE_NO_WINDOW if os.name == "nt" else 0
            containers_with_restart = []

            try:
                for container_id in selected_containers:
                    result = subprocess.run(
                        DOCKER_CMD_PREFIX
                        + [
                            "inspect",
                            "--format",
                            "{{.HostConfig.RestartPolicy.Name}}",
                            container_id,
                        ],
                        capture_output=True,
                        text=True,
                        creationflags=flags,
                    )
                    restart_policy = result.stdout.strip()
                    if restart_policy in ["always", "unless-stopped"]:
                        containers_with_restart.append(container_id)

                if containers_with_restart:
                    response = messagebox.askyesno(
                        "Restart Policy Detected",
                        f"{len(containers_with_restart)} container(s) have restart policies.\n\n"
                        f"They will automatically restart after stopping.\n"
                        f"Remove restart policies before stopping?",
                    )
                    if response:
                        for container_id in containers_with_restart:
                            subprocess.run(
                                DOCKER_CMD_PREFIX
                                + ["update", "--restart=no", container_id],
                                capture_output=True,
                                creationflags=flags,
                            )
            except:
                pass

        for container_id in selected_containers:
            self._execute_command(
                [action, container_id],
                success_message=f"Container {container_id[:12]} {action}ed successfully.",
                error_message=f"Failed to {action} container {container_id[:12]}.",
            )

        self.refresh_containers()

    def prune_containers(self):
        """Remove all stopped containers"""
        if not messagebox.askyesno(
            "Confirm Prune", "Are you sure you want to remove ALL stopped containers?"
        ):
            return

        success, output = self._execute_command(
            ["container", "prune", "-f"],
            success_message="Exited containers pruned.",
            error_message="Failed to prune exited containers.",
        )
        if success:
            messagebox.showinfo("Prune Success", output)
            self.refresh_containers()

    def exec_terminal(self):
        """Execute interactive terminal in selected container"""
        container_id = self._get_selected_id(self.containers_tree)
        if not container_id:
            return

        selected_item_values = self.containers_tree.item(container_id, "values")
        if "Up" not in selected_item_values[3]:
            messagebox.showwarning(
                "Container Not Running",
                "Cannot open a terminal on a stopped container. Please start it first.",
            )
            return

        command = [
            "start",
            "wsl",
            "docker",
            "exec",
            "-it",
            container_id,
            "sh",
            "-c",
            "exec /bin/bash || exec /bin/sh",
        ]

        try:
            subprocess.Popen(command, shell=True)
        except Exception as e:
            messagebox.showerror(
                "Execution Error", f"Failed to open terminal window: {e}"
            )

    # === IMAGE TAB ===

    def create_image_tab(self):
        image_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(image_frame, text="Images")

        columns = ("ID", "Repository", "Tag", "Size")
        self.images_tree = ttk.Treeview(image_frame, columns=columns, show="headings")
        self.images_tree.pack(fill="both", expand=True)

        for col in columns:
            self.images_tree.heading(col, text=col)
            self.images_tree.column(col, anchor=tk.W, width=150)

        vsb = ttk.Scrollbar(
            image_frame, orient="vertical", command=self.images_tree.yview
        )
        vsb.pack(side="right", fill="y")
        self.images_tree.configure(yscrollcommand=vsb.set)
        self.images_tree.bind(
            "<Control-a>", lambda e: self.select_all(self.images_tree)
        )

        button_frame = ttk.Frame(image_frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="Refresh", command=self.refresh_images).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Remove Image", command=self.remove_image).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Prune Dangling", command=self.prune_images).pack(
            side=tk.LEFT, padx=5
        )

    def select_all(self, tree):
        """Select all items in treeview"""
        tree.selection_set(tree.get_children())
        return "break"

    def refresh_images(self):
        """Fetch and display images"""
        success, output = self._execute_command(
            ["images", "--format", "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}"],
            success_message="Images refreshed.",
        )

        for item in self.images_tree.get_children():
            self.images_tree.delete(item)

        if success and output:
            for line in output.strip().split("\n"):
                if line:
                    try:
                        iid, repo, tag, size = line.split("\t", 3)
                        self.images_tree.insert(
                            "", tk.END, values=(iid[:12], repo, tag, size), iid=iid
                        )
                    except ValueError:
                        print(f"Skipping malformed image output line: {line}")

    def remove_image(self):
        """Remove selected images"""
        selected_images = self.images_tree.selection()

        if not selected_images:
            messagebox.showwarning(
                "Selection Required", "Please select image(s) first."
            )
            return

        count = len(selected_images)
        if not messagebox.askyesno(
            "Confirm Removal", f"Are you sure you want to remove {count} image(s)?"
        ):
            return

        for image_id in selected_images:
            self._execute_command(
                ["rmi", "-f", image_id],
                success_message=f"Image {image_id[:12]} removed successfully.",
                error_message=f"Failed to remove image {image_id[:12]}.",
            )

        self.refresh_images()

    def prune_images(self):
        """Remove all dangling images"""
        if not messagebox.askyesno(
            "Confirm Prune", "Are you sure you want to remove ALL dangling images?"
        ):
            return

        success, output = self._execute_command(
            ["image", "prune", "-f"],
            success_message="Dangling images pruned.",
            error_message="Failed to prune images.",
        )
        if success:
            messagebox.showinfo("Prune Success", output)
            self.refresh_images()

    # === VOLUME TAB ===

    def create_volume_tab(self):
        volume_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(volume_frame, text="Volumes")

        columns = ("Name", "Driver")
        self.volumes_tree = ttk.Treeview(volume_frame, columns=columns, show="headings")
        self.volumes_tree.pack(fill="both", expand=True)

        for col in columns:
            self.volumes_tree.heading(col, text=col)
            self.volumes_tree.column(col, anchor=tk.W, width=300)

        vsb = ttk.Scrollbar(
            volume_frame, orient="vertical", command=self.volumes_tree.yview
        )
        vsb.pack(side="right", fill="y")
        self.volumes_tree.configure(yscrollcommand=vsb.set)
        self.volumes_tree.bind(
            "<Control-a>", lambda e: self.select_all(self.volumes_tree)
        )

        button_frame = ttk.Frame(volume_frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="Refresh", command=self.refresh_volumes).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Remove Volume", command=self.remove_volume).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Prune Unused", command=self.prune_volumes).pack(
            side=tk.LEFT, padx=5
        )

    def refresh_volumes(self):
        """Fetch and display volumes"""
        success, output = self._execute_command(
            ["volume", "ls", "--format", "{{.Name}}\t{{.Driver}}"],
            success_message="Volumes refreshed.",
        )

        for item in self.volumes_tree.get_children():
            self.volumes_tree.delete(item)

        if success and output:
            for line in output.strip().split("\n"):
                if line:
                    try:
                        name, driver = line.split("\t", 1)
                        self.volumes_tree.insert(
                            "", tk.END, values=(name, driver), iid=name
                        )
                    except ValueError:
                        print(f"Skipping malformed volume output line: {line}")

    def remove_volume(self):
        """Remove selected volumes"""
        selected_volumes = self.volumes_tree.selection()

        if not selected_volumes:
            messagebox.showwarning(
                "Selection Required", "Please select volume(s) first."
            )
            return

        count = len(selected_volumes)
        response = messagebox.askyesnocancel(
            "Confirm Removal",
            f"Remove {count} volume(s)?\n\n"
            f"Yes = Normal remove\n"
            f"No = Force remove (removes even if in use)\n"
            f"Cancel = Abort",
        )

        if response is None:
            return

        force_flag = ["-f"] if response is False else []

        for volume_name in selected_volumes:
            self._execute_command(
                ["volume", "rm"] + force_flag + [volume_name],
                success_message=f"Volume {volume_name} removed successfully.",
                error_message=f"Failed to remove volume {volume_name}.",
            )

        self.refresh_volumes()

    def prune_volumes(self):
        """Remove all unused volumes"""
        if not messagebox.askyesno(
            "Confirm Prune", "Are you sure you want to remove ALL unused volumes?"
        ):
            return

        success, output = self._execute_command(
            ["volume", "prune", "-f"],
            success_message="Unused volumes pruned.",
            error_message="Failed to prune volumes.",
        )
        if success:
            messagebox.showinfo("Prune Success", output)
            self.refresh_volumes()

    # === LOGS IMPLEMENTATION ===

    def _get_wsl_current_time(self):
        """Fetch current UTC time from WSL"""
        command = ["date", "-u", "+%Y-%m-%dT%H:%M:%S.%NZ"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except:
            return None

    def _safe_remove_log_thread(self, thread_instance):
        """Safely remove thread from active list"""
        try:
            if thread_instance in self.active_log_threads:
                self.active_log_threads.remove(thread_instance)
        except Exception as e:
            print(f"Warning: Failed to remove thread {thread_instance.name}: {e}")

    def _show_datetime_picker(self, master, target_var):
        """Open datetime picker dialog"""
        cal_window = tk.Toplevel(master)
        cal_window.title("Select Date and Time")
        cal_window.transient(master)

        hour_var = tk.IntVar(value=datetime.now().hour)
        minute_var = tk.IntVar(value=datetime.now().minute)
        second_var = tk.IntVar(value=datetime.now().second)

        today = date.today()
        cal = tkc.Calendar(
            cal_window,
            selectmode="day",
            year=today.year,
            month=today.month,
            day=today.day,
            date_pattern="y-mm-dd",
        )
        cal.pack(pady=10, padx=10)

        time_frame = ttk.Frame(cal_window)
        time_frame.pack(pady=5, padx=10)

        ttk.Label(time_frame, text="Time (HH:MM:SS):").pack(side=tk.LEFT)
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=23,
            width=3,
            wrap=True,
            textvariable=hour_var,
            format="%02.0f",
        ).pack(side=tk.LEFT, padx=2)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=59,
            width=3,
            wrap=True,
            textvariable=minute_var,
            format="%02.0f",
        ).pack(side=tk.LEFT, padx=2)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=59,
            width=3,
            wrap=True,
            textvariable=second_var,
            format="%02.0f",
        ).pack(side=tk.LEFT, padx=2)

        def set_datetime():
            selected_date_str = cal.get_date()
            time_str = (
                f"{hour_var.get():02d}:"
                f"{minute_var.get():02d}:"
                f"{second_var.get():02d}.000000000Z"
            )
            new_timestamp = f"{selected_date_str}T{time_str}"
            target_var.set(new_timestamp)
            cal_window.destroy()

        ttk.Button(cal_window, text="Set Datetime", command=set_datetime).pack(pady=10)
        cal_window.grab_set()
        master.wait_window(cal_window)

    def show_logs(self):
        """Open log streaming window for selected container"""
        container_id = self._get_selected_id(self.containers_tree)
        if not container_id:
            return

        container_name = self.containers_tree.item(container_id, "values")[1]

        log_window = tk.Toplevel(self.root)
        log_window.title(f"Logs: {container_name} ({container_id[:12]})")

        try:
            icon_path = resource_path("nano_whale.ico")
            log_window.iconbitmap(icon_path)
        except:
            pass

        log_window.update_idletasks()
        screen_width = log_window.winfo_screenwidth()
        window_width = screen_width // 2
        window_height = 800
        log_window.geometry(f"{window_width}x{window_height}")

        control_frame = ttk.Frame(log_window)
        control_frame.pack(fill="x", padx=10, pady=5)

        log_text = scrolledtext.ScrolledText(
            log_window,
            wrap=tk.WORD,
            state=tk.NORMAL,
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 10),
        )
        log_text.pack(expand=True, fill="both", padx=10, pady=10)

        from_time_var = tk.StringVar(value="")
        to_time_var = tk.StringVar(value="")
        timestamp_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            control_frame,
            text="Show Timestamps (-t)",
            variable=timestamp_var,
            command=lambda: restart_log_stream(mode="timestamp_toggle"),
        ).pack(side=tk.LEFT, padx=10)

        ttk.Label(control_frame, text="From (RFC3339):").pack(side=tk.LEFT, padx=5)
        from_entry = ttk.Entry(control_frame, textvariable=from_time_var, width=25)
        from_entry.pack(side=tk.LEFT, padx=1)
        ttk.Button(
            control_frame,
            text="📅🕐",
            command=lambda: self._show_datetime_picker(log_window, from_time_var),
        ).pack(side=tk.LEFT, padx=(0, 1))

        ttk.Label(control_frame, text="To (RFC3339):").pack(side=tk.LEFT, padx=5)
        to_entry = ttk.Entry(control_frame, textvariable=to_time_var, width=25)
        to_entry.pack(side=tk.LEFT, padx=1)
        ttk.Button(
            control_frame,
            text="📅🕗",
            command=lambda: self._show_datetime_picker(log_window, to_time_var),
        ).pack(side=tk.LEFT, padx=(0, 1))

        ttk.Button(
            control_frame,
            text="Apply Range Filter",
            command=lambda: restart_log_stream(mode="range"),
        ).pack(side=tk.LEFT, padx=10)

        def thread_exit_callback(thread_instance):
            self._safe_remove_log_thread(thread_instance)

        def restart_log_stream(mode="clear", since_time=None, until_time=None):
            nonlocal log_thread

            show_timestamps = timestamp_var.get()
            log_thread.terminate()

            log_text.config(state=tk.NORMAL)
            log_text.delete("1.0", tk.END)
            log_text.config(state=tk.DISABLED)

            if mode == "range":
                since_time = from_time_var.get() if from_time_var.get() else None
                until_time = to_time_var.get() if to_time_var.get() else None
            elif mode == "history":
                since_time = None
                until_time = None
            elif mode == "clear":
                since_time = self._get_wsl_current_time()
                until_time = None
                if not since_time:
                    log_text.after(
                        0,
                        log_text.insert,
                        tk.END,
                        f"--- ERROR: Could not fetch time. Stream failed. ---\n",
                    )
                    log_text.see(tk.END)
                    return
            elif mode == "timestamp_toggle":
                since_time = log_thread.since_time
                until_time = log_thread.until_time
            else:
                log_text.after(
                    0, log_text.insert, tk.END, "\n--- Stream format updated ---\n"
                )
                log_text.see(tk.END)

            new_log_thread = LogStreamer(
                container_id,
                log_text,
                lambda instance: thread_exit_callback(new_log_thread),
                since_time=since_time,
                until_time=until_time,
                show_timestamps=show_timestamps,
            )

            try:
                self.active_log_threads.remove(log_thread)
            except ValueError:
                self._safe_remove_log_thread(log_thread)

            self.active_log_threads.append(new_log_thread)
            log_window.bind("<Destroy>", lambda e: new_log_thread.terminate())
            new_log_thread.start()

            log_thread = new_log_thread

        log_thread = LogStreamer(
            container_id,
            log_text,
            lambda instance: self._safe_remove_log_thread(instance),
            since_time=self._get_wsl_current_time(),
            until_time=None,
            show_timestamps=timestamp_var.get(),
        )
        self.active_log_threads.append(log_thread)
        log_thread.start()

        button_frame = ttk.Frame(log_window)
        button_frame.pack(pady=5)

        ttk.Button(
            button_frame,
            text="Show History",
            command=lambda: restart_log_stream(mode="history"),
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Clear",
            command=lambda: restart_log_stream(mode="clear"),
        ).pack(side=tk.LEFT, padx=(20, 5))

        ttk.Button(button_frame, text="Close", command=log_window.destroy).pack(
            side=tk.LEFT, padx=5
        )

        log_window.bind("<Destroy>", lambda e: log_thread.terminate())

    # === DEPLOYMENT FUNCTIONS ===

    def check_docker_files_for_dependency(self, dependency_name):
        """Check if a dependency is handled in Docker files"""
        docker_files = [
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ]

        search_terms = {
            "node": ["node:", "FROM node", "nodejs", "npm install", "yarn install"],
            "python": ["python:", "FROM python", "pip install", "requirements.txt"],
            "ruby": ["ruby:", "FROM ruby", "bundle install", "Gemfile"],
            "go": ["golang:", "FROM golang", "go build", "go.mod"],
        }

        terms = search_terms.get(dependency_name.lower(), [])
        if not terms:
            return False

        for dockerfile in docker_files:
            filepath = os.path.join(self.clone_dir, dockerfile)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read().lower()
                        for term in terms:
                            if term.lower() in content:
                                return True
                except:
                    continue

        return False

    def get_installed_version(self, command, version_arg="--version"):
        """Get installed version of a tool"""
        print("here command:", command, "version_arg:", version_arg)
        try:
            result = subprocess.run(
                [command, version_arg],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            print("ningga", result)
            print(result.stdout)
            if result.returncode == 0:
                # Extract version number from output
                version_text = result.stdout.strip()
                # Try to find version pattern like x.y.z
                import re

                version_match = re.search(r"(\d+\.\d+\.\d+|\d+\.\d+)", version_text)
                if version_match:
                    return version_match.group(1)
                return version_text
        except Exception as e:
            print("Error occurred while getting installed version:", e)
            pass
        return None

    def check_package_manager(self):
        self._refresh_env_vars()
        time.sleep(5)

        """Check if Chocolatey or Scoop is installed"""
        choco = self.get_installed_version("choco", "--version")
        scoop = self.get_installed_version("scoop", "--version")

        if choco:
            return "choco", choco
        elif scoop:
            return "scoop", scoop
        return None, None

    def install_package_manager(self):
        print("Installing Chocolatey package manager...")
        pkg_mgr, version = self.check_package_manager()
        if pkg_mgr:
            self.deploy_log(f"✓ Chocolatey {version} already installed ", "MEH")
            return
        """Install Chocolatey package manager"""
        self.deploy_log("Installing Chocolatey package manager...", "INSTALL")

        install_script = (
            "Set-ExecutionPolicy Bypass -Scope Process -Force; "
            "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; "
            "iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
        )

        try:
            subprocess.run(
                ["powershell", "-Command", install_script],
                capture_output=True,
                text=True,
                timeout=300,
            )
            time.sleep(2)

            # Verify installation
            pkg_mgr, version = self.check_package_manager()
            if pkg_mgr:
                self.deploy_log(
                    f"✓ Chocolatey {version} installed successfully", "SUCCESS"
                )
                return True
            else:
                self.deploy_log("✗ Chocolatey installation failed", "ERROR")
                return False
        except Exception as e:
            self.deploy_log(f"✗ Failed to install Chocolatey: {e}", "ERROR")
            return False

    def install_local_dependencies(self):
        """Install required local dependencies"""
        if not self.local_deps_needed:
            messagebox.showinfo("Info", "No local dependencies need to be installed.")
            return

        self.install_local_deps_btn.config(state=tk.DISABLED)
        self.deploy_log("=" * 80)
        self.deploy_log("🔧 Starting local dependency installation...", "INSTALL")

        def install_thread():
            try:
                # Check package manager
                pkg_mgr, version = self.check_package_manager()

                if not pkg_mgr:
                    self.deploy_log(
                        "Package manager not found. Installing Chocolatey...", "INSTALL"
                    )
                    if not self.install_package_manager():
                        self.deploy_log(
                            "✗ Cannot proceed without package manager", "ERROR"
                        )
                        return
                    pkg_mgr = "choco"

                self.deploy_log(f"Using {pkg_mgr} package manager", "INFO")

                for dep_name, dep_info in self.local_deps_needed.items():
                    required_version = dep_info.get("required_version")
                    current_version = dep_info.get("current_version")

                    self.deploy_log(f"Processing {dep_name}...", "INFO")

                    # Map dependency names to package names
                    package_map = {
                        "Node.js": "nodejs",
                        "Python": "python",
                        "Ruby": "ruby",
                        "Go": "golang",
                    }

                    package_name = package_map.get(dep_name, dep_name.lower())

                    # Determine install command
                    if pkg_mgr == "choco":
                        if current_version:
                            # Upgrade existing
                            cmd = f"choco upgrade {package_name} -y"
                        else:
                            # Fresh install
                            if required_version and required_version != "Any version":
                                cmd = f"choco install {package_name} --version={required_version} -y"
                            else:
                                cmd = f"choco install {package_name} -y"
                    else:  # scoop
                        if current_version:
                            cmd = f"scoop update {package_name}"
                        else:
                            cmd = f"scoop install {package_name}"

                    self.deploy_log(f"Executing: {cmd}", "INFO")

                    # Run in elevated PowerShell for choco
                    if pkg_mgr == "choco":
                        ps_cmd = f"Start-Process powershell -Verb RunAs -ArgumentList '-Command', '{cmd}' -Wait"
                        subprocess.run(
                            ["powershell", "-Command", ps_cmd],
                            capture_output=True,
                            text=True,
                            timeout=600,
                        )
                    else:
                        subprocess.run(
                            cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=600,
                        )

                    time.sleep(2)

                    # Verify installation
                    command_map = {
                        "Node.js": "node",
                        "Python": "python",
                        "Ruby": "ruby",
                        "Go": "go",
                    }

                    verify_cmd = command_map.get(dep_name, dep_name.lower())
                    new_version = self.get_installed_version(verify_cmd)

                    if new_version:
                        self.deploy_log(
                            f"✓ {dep_name} {new_version} installed/updated", "SUCCESS"
                        )
                    else:
                        self.deploy_log(
                            f"⚠ {dep_name} installation could not be verified",
                            "WARNING",
                        )

                self.deploy_log("=" * 80)
                self.deploy_log(
                    "🎉 Local dependency installation completed!", "SUCCESS"
                )
                self.deploy_log(
                    "ℹ️ You may need to restart your terminal/IDE to use new installations",
                    "INFO",
                )

                # Re-analyze to update status
                self.root.after(0, self.analyze_repo)

                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Success",
                        "Local dependencies installed!\n\nYou may need to restart your terminal or IDE.",
                    ),
                )

            except Exception as e:
                self.deploy_log(f"✗ Installation failed: {str(e)}", "ERROR")
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Installation failed: {str(e)}"
                    ),
                )
            finally:
                self.root.after(
                    0, lambda: self.install_local_deps_btn.config(state=tk.NORMAL)
                )

        threading.Thread(target=install_thread, daemon=True).start()

    def analyze_repo(self):
        """Analyze repository (recursively) for dependencies and local installation needs"""
        self.deploy_log("Analyzing repository for dependencies...")

        def analyze():
            if not os.path.exists(self.clone_dir):
                self.deploy_log(
                    "Repository not cloned yet. Please deploy first.", "WARNING"
                )
                return

            self.detected_deps = {}
            self.local_deps_needed = {}
            self.installed_versions = {}

            def find_files_recursively(root_dir, filenames):
                """Return all paths that match any filename in list"""
                found = []
                for dirpath, _, files in os.walk(root_dir):
                    for f in files:
                        if f in filenames:
                            found.append(os.path.join(dirpath, f))
                return found

            # --- Node.js dependencies ---
            node_required_version = None
            package_json_files = find_files_recursively(
                self.clone_dir, ["package.json"]
            )
            for package_json in package_json_files:
                try:
                    with open(package_json, "r") as f:
                        data = json.load(f)
                        if "engines" in data and "node" in data["engines"]:
                            node_required_version = data["engines"]["node"]
                            self.detected_deps[
                                f"Node.js ({os.path.relpath(package_json, self.clone_dir)})"
                            ] = node_required_version
                        else:
                            self.detected_deps[
                                f"Node.js ({os.path.relpath(package_json, self.clone_dir)})"
                            ] = "Any version"
                except Exception:
                    pass

            # --- Python dependencies ---
            for req in find_files_recursively(self.clone_dir, ["requirements.txt"]):
                self.detected_deps[
                    f"Python ({os.path.relpath(req, self.clone_dir)})"
                ] = "Required"

            # --- Ruby dependencies ---
            for gemfile in find_files_recursively(self.clone_dir, ["Gemfile"]):
                self.detected_deps[
                    f"Ruby ({os.path.relpath(gemfile, self.clone_dir)})"
                ] = "Required"

            # --- Go dependencies ---
            go_required_version = None
            for gomod in find_files_recursively(self.clone_dir, ["go.mod"]):
                try:
                    with open(gomod, "r") as f:
                        content = f.read()
                        match = re.search(r"go (\d+\.\d+)", content)
                        if match:
                            go_required_version = match.group(1)
                            self.detected_deps[
                                f"Go ({os.path.relpath(gomod, self.clone_dir)})"
                            ] = go_required_version
                except Exception:
                    pass

            # --- Docker Compose files ---
            compose_files = find_files_recursively(
                self.clone_dir,
                [
                    "docker-compose.yml",
                    "docker-compose.yaml",
                    "compose.yml",
                    "compose.yaml",
                ],
            )
            if compose_files:
                self.detected_deps["Docker Compose"] = (
                    f"Found in: {', '.join([os.path.relpath(f, self.clone_dir) for f in compose_files])}"
                )

            # --- .nvmrc files ---
            for nvmrc in find_files_recursively(self.clone_dir, [".nvmrc"]):
                try:
                    with open(nvmrc, "r") as f:
                        nvmrc_version = f.read().strip()
                        rel = os.path.relpath(nvmrc, self.clone_dir)
                        self.detected_deps[f"Node.js (from {rel})"] = nvmrc_version
                        if not node_required_version:
                            node_required_version = nvmrc_version
                except Exception:
                    pass

            # --- Local installation needs ---
            if any("Node.js" in k for k in self.detected_deps):
                if not self.check_docker_files_for_dependency("node"):
                    installed_node = self.get_installed_version("node", "--version")
                    self.installed_versions["Node.js"] = installed_node

                    needs_install = False
                    if not installed_node:
                        needs_install = True
                    elif (
                        node_required_version and node_required_version != "Any version"
                    ):
                        needs_install = not self.version_matches(
                            installed_node, node_required_version
                        )

                    if needs_install or not installed_node:
                        self.local_deps_needed["Node.js"] = {
                            "required_version": node_required_version or "latest",
                            "current_version": installed_node,
                            "reason": "Not containerized in Docker",
                        }

            if any("Python" in k for k in self.detected_deps):
                if not self.check_docker_files_for_dependency("python"):
                    installed_python = self.get_installed_version("python", "--version")
                    self.installed_versions["Python"] = installed_python

                    if not installed_python:
                        self.local_deps_needed["Python"] = {
                            "required_version": "latest",
                            "current_version": None,
                            "reason": "Not containerized in Docker",
                        }

            if any("Ruby" in k for k in self.detected_deps):
                if not self.check_docker_files_for_dependency("ruby"):
                    installed_ruby = self.get_installed_version("ruby", "--version")
                    self.installed_versions["Ruby"] = installed_ruby

                    if not installed_ruby:
                        self.local_deps_needed["Ruby"] = {
                            "required_version": "latest",
                            "current_version": None,
                            "reason": "Not containerized in Docker",
                        }

            if any("Go" in k for k in self.detected_deps):
                if not self.check_docker_files_for_dependency("go"):
                    installed_go = self.get_installed_version("go", "version")
                    self.installed_versions["Go"] = installed_go

                    needs_install = False
                    if not installed_go:
                        needs_install = True
                    elif go_required_version:
                        needs_install = not self.version_matches(
                            installed_go, go_required_version
                        )

                    if needs_install or not installed_go:
                        self.local_deps_needed["Go"] = {
                            "required_version": go_required_version or "latest",
                            "current_version": installed_go,
                            "reason": "Not containerized in Docker",
                        }

            # --- Update UI ---
            def update_deps():
                self.deps_text.delete("1.0", tk.END)
                if self.detected_deps:
                    for dep, version in self.detected_deps.items():
                        self.deps_text.insert(tk.END, f"✓ {dep}: {version}\n")
                else:
                    self.deps_text.insert(
                        tk.END, "No specific dependencies detected in repository.\n"
                    )
                self.deps_text.insert(
                    tk.END, "\n📋 Searched all subdirectories for dependency files."
                )

                self.local_deps_text.delete("1.0", tk.END)
                if self.local_deps_needed:
                    self.local_deps_text.insert(
                        tk.END,
                        "⚠️ The following dependencies need LOCAL installation:\n\n",
                        "warning",
                    )
                    for dep, info in self.local_deps_needed.items():
                        current = info["current_version"] or "Not installed"
                        required = info["required_version"]
                        reason = info["reason"]

                        self.local_deps_text.insert(tk.END, f"📦 {dep}:\n")
                        self.local_deps_text.insert(
                            tk.END, f"   Required: {required}\n"
                        )
                        self.local_deps_text.insert(tk.END, f"   Current: {current}\n")
                        self.local_deps_text.insert(tk.END, f"   Reason: {reason}\n\n")

                    self.install_local_deps_btn.config(state=tk.NORMAL)
                else:
                    self.local_deps_text.insert(
                        tk.END,
                        "✓ All dependencies are either installed locally or handled by Docker.\n\nNo local installation needed!",
                    )
                    self.install_local_deps_btn.config(state=tk.DISABLED)

            self.root.after(0, update_deps)
            self.deploy_log("✓ Recursive repository analysis complete", "SUCCESS")

        threading.Thread(target=analyze, daemon=True).start()

    def version_matches(self, installed_version, required_version):
        """Check if installed version matches required version"""
        if not installed_version or not required_version:
            return False

        # Clean version strings
        installed_clean = re.search(r"(\d+\.\d+\.\d+|\d+\.\d+)", installed_version)
        required_clean = re.search(r"(\d+\.\d+\.\d+|\d+\.\d+)", str(required_version))

        if not installed_clean or not required_clean:
            return False

        installed_parts = [int(x) for x in installed_clean.group(1).split(".")]
        required_parts = [int(x) for x in required_clean.group(1).split(".")]

        # Pad shorter version with zeros
        while len(installed_parts) < len(required_parts):
            installed_parts.append(0)
        while len(required_parts) < len(installed_parts):
            required_parts.append(0)

        # Check if major.minor matches (allowing different patch versions)
        if len(installed_parts) >= 2 and len(required_parts) >= 2:
            return (
                installed_parts[0] == required_parts[0]
                and installed_parts[1] == required_parts[1]
            )

        return installed_parts == required_parts

    def refresh_branches(self):
        """Fetch available branches from remote repository"""
        self.deploy_log("Fetching branches...")

        def fetch_branches():
            url = self.get_repo_url_with_token()
            cmd = f"git ls-remote --heads {url}"
            success, stdout, stderr = self.run_command(cmd)

            if success and stdout:
                branches = []
                for line in stdout.strip().split("\n"):
                    if line:
                        branch = line.split("refs/heads/")[-1]
                        branches.append(branch)

                self.root.after(0, lambda: self.branch_combo.config(values=branches))

                if branches:
                    self.root.after(0, lambda: self.branch_var.set(branches[0]))

                self.deploy_log(f"✓ Found {len(branches)} branches")
            else:
                self.deploy_log(f"Failed to fetch branches: {stderr}", "ERROR")

        threading.Thread(target=fetch_branches, daemon=True).start()

    def get_repo_url_with_token(self):
        """Construct repository URL with token"""
        url = self.repo_url_entry.get()
        token = self.token_entry.get()

        if token and "github.com" in url:
            url = url.replace("https://", f"https://{token}@")
        return url

    def execute_command_pipeline(self, commands, base_cwd=None, background_mode=False):
        """Execute a list of commands with directory tracking"""
        current_dir = base_cwd or self.clone_dir

        for cmd in commands:
            cmd = cmd.strip()
            if not cmd or cmd.startswith("#"):
                continue

            if cmd.startswith("cd "):
                new_path = cmd[3:].strip()
                if new_path.startswith("/"):
                    current_dir = os.path.join(self.clone_dir, new_path.lstrip("/"))
                else:
                    current_dir = os.path.join(current_dir, new_path)

                self.deploy_log(f"📁 Changed directory to: {current_dir}")

            is_background_cmd = any(
                keyword in cmd.lower()
                for keyword in [
                    "npm run dev",
                    "npm start",
                    "yarn dev",
                    "pnpm dev",
                    "--watch",
                ]
            )

            if is_background_cmd or background_mode:
                self.deploy_log(f"🚀 Starting in new terminal: {cmd}")

                try:
                    subprocess.Popen(
                        f"start cmd /k {cmd}",
                        shell=True,
                        cwd=current_dir,
                    )
                    self.deploy_log(f"✓ Started in background terminal")
                    time.sleep(1)
                except Exception as e:
                    self.deploy_log(f"✗ Failed to launch terminal: {e}", "ERROR")
                    return False
            else:
                self.deploy_log(f"⚙ Executing: {cmd}")

                if cmd.startswith("docker"):
                    cmd = f"wsl {cmd}"

                success, stdout, stderr = self.run_command(
                    cmd, cwd=current_dir, timeout=600
                )

                if stdout:
                    self.deploy_log(stdout.strip())

                if not success:
                    self.deploy_log(f"✗ Command failed: {stderr}", "ERROR")
                    return False

        return True

    def deploy(self):
        """Main deployment function"""
        self.deploy_log("=" * 80)
        self.deploy_log("🚀 Starting deployment process...")
        self.deploy_btn.config(state=tk.DISABLED)

        def deploy_thread():
            try:
                self.repo_url = self.repo_url_entry.get()
                self.git_token = self.token_entry.get()
                self.repo_name = self.repo_name_entry.get()
                self.clone_dir = os.path.join(os.getcwd(), self.repo_name)

                branch = self.branch_var.get()

                if not os.path.exists(self.clone_dir):
                    self.deploy_log(f"📦 Cloning repository to {self.clone_dir}...")
                    url = self.get_repo_url_with_token()
                    success, stdout, stderr = self.run_command(
                        f"git clone -b {branch} {url} {self.repo_name}"
                    )
                    if not success:
                        self.deploy_log(f"✗ Clone failed: {stderr}", "ERROR")
                        return
                    self.deploy_log("✓ Repository cloned successfully!")
                else:
                    self.deploy_log(
                        f"📥 Pulling latest changes for branch '{branch}'..."
                    )
                    self.run_command(f"git checkout {branch}", cwd=self.clone_dir)
                    success, stdout, stderr = self.run_command(
                        f"git pull origin {branch}", cwd=self.clone_dir
                    )
                    if not success:
                        self.deploy_log(f"✗ Pull failed: {stderr}", "ERROR")
                        return
                    self.deploy_log("✓ Repository updated successfully!")

                self.deploy_log("Copying .env file to repository...")
                if os.path.exists(self.env_path):
                    target_env = os.path.join(self.clone_dir, ".env")
                    shutil.copy2(self.env_path, target_env)
                    self.deploy_log("✓ .env file copied")
                else:
                    self.deploy_log("⚠ .env file not found, skipping", "WARNING")

                pre_cmds = self.get_commands_from_text(self.pre_deploy_text)
                if pre_cmds:
                    self.deploy_log("⚙ Running pre-deploy commands...")
                    if not self.execute_command_pipeline(pre_cmds):
                        self.deploy_log("✗ Pre-deploy failed", "ERROR")
                        return
                    self.deploy_log("✓ Pre-deploy commands completed")

                docker_cmds = self.get_commands_from_text(self.docker_text)
                if docker_cmds:
                    self.deploy_log("🐳 Running Docker commands...")
                    if not self.execute_command_pipeline(docker_cmds):
                        self.deploy_log("✗ Docker deployment failed", "ERROR")
                        return
                    self.deploy_log("✓ Docker containers started successfully!")

                post_cmds = self.get_commands_from_text(self.post_deploy_text)
                if post_cmds:
                    self.deploy_log("⚙ Running post-deploy commands...")
                    post_cmds_result = self.execute_command_pipeline(post_cmds)
                    if not post_cmds_result:
                        self.deploy_log("⚠ Some post-deploy commands failed", "WARNING")
                    else:
                        self.deploy_log("✓ Post-deploy commands completed")

                self.deploy_log("=" * 80)
                self.deploy_log("🎉 Deployment completed successfully!", "SUCCESS")

                # Refresh container list after deployment
                self.root.after(0, self.refresh_containers)

                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Success", "Deployment completed successfully!"
                    ),
                )

            except Exception as e:
                self.deploy_log(f"✗ Deployment failed: {str(e)}", "ERROR")
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Deployment failed: {str(e)}"
                    ),
                )
            finally:
                self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))

        threading.Thread(target=deploy_thread, daemon=True).start()

    def stop_services(self):
        """Stop Docker containers"""
        self.deploy_log("⏹ Stopping services...")

        def stop():
            if os.path.exists(self.clone_dir):
                docker_cmds = self.get_commands_from_text(self.docker_text)
                stop_cmds = []
                for cmd in docker_cmds:
                    if "up" in cmd:
                        stop_cmd = cmd.replace("up -d", "down").replace("up", "down")
                        stop_cmds.append(stop_cmd)

                if not stop_cmds:
                    stop_cmds = ["docker compose down"]

                self.execute_command_pipeline(stop_cmds)
                self.deploy_log("✓ Services stopped", "SUCCESS")

                # Refresh container list after stopping
                self.root.after(0, self.refresh_containers)
            else:
                self.deploy_log("No deployment found to stop", "WARNING")

        threading.Thread(target=stop, daemon=True).start()

    def clean_clone_dir(self):
        """Remove cloned repository directory"""
        if os.path.exists(self.clone_dir):
            result = messagebox.askyesno(
                "Confirm Deletion",
                f"Are you sure you want to delete {self.clone_dir}?\nThis cannot be undone.",
            )
            if result:
                try:
                    shutil.rmtree(self.clone_dir)
                    self.deploy_log(f"✓ Deleted {self.clone_dir}", "SUCCESS")
                except Exception as e:
                    self.deploy_log(f"✗ Failed to delete: {e}", "ERROR")
        else:
            self.deploy_log("No clone directory to delete", "INFO")


class LogStreamer(threading.Thread):
    """Thread to stream Docker logs using subprocess.Popen"""

    def __init__(
        self,
        container_id,
        text_widget,
        on_exit_callback,
        since_time=None,
        until_time=None,
        show_timestamps=True,
    ):
        super().__init__()
        self.container_id = container_id
        self.text_widget = text_widget
        self.on_exit_callback = on_exit_callback
        self.since_time = since_time
        self.until_time = until_time
        self.show_timestamps = show_timestamps
        self.log_process = None
        self.daemon = True
        self.running = True

    def run(self):
        command = DOCKER_CMD_PREFIX + ["logs"]

        if self.show_timestamps:
            command.append("-t")

        if not self.until_time:
            command.append("-f")

        if self.since_time:
            command.append(f"--since={self.since_time}")

        if self.until_time:
            command.append(f"--until={self.until_time}")

        command.append(self.container_id)

        try:
            self.log_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW,
            )

            for line in iter(self.log_process.stdout.readline, ""):
                if not self.running or self.log_process.poll() is not None:
                    break
                self.text_widget.after(0, self.append_text, line)

            if self.log_process.wait() == 0 and self.until_time:
                self.text_widget.after(
                    0,
                    self.append_text,
                    f"\n--- Log stream finished at {self.until_time}. No more logs. ---\n",
                )

        except Exception as e:
            self.text_widget.after(
                0, self.append_text, f"\n--- ERROR: Log Streamer failed: {e} ---\n"
            )
        finally:
            self.running = False
            if self.log_process and self.log_process.poll() is None:
                self.log_process.terminate()
            self.on_exit_callback(self)

    def append_text(self, content):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, content)
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)

    def terminate(self):
        self.running = False
        if self.log_process and self.log_process.poll() is None:
            self.log_process.terminate()


def main():
    # Check if running as Administrator
    if os.name == "nt":
        try:
            is_admin = windll.shell32.IsUserAnAdmin()
            if not is_admin:
                print("WARNING: Not running as Administrator.")
                print("WSL installation will require Administrator privileges.")
        except:
            pass

    root = tk.Tk()

    # Set theme
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        style.theme_use("clam")

    try:
        app = UniversalDockerManager(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror(
            "Application Error", f"The application failed to start: {e}"
        )
        root.destroy()


if __name__ == "__main__":
    main()
