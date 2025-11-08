import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import windll
from datetime import date, datetime
from tkinter import messagebox, scrolledtext, ttk

import tkcalendar as tkc  # Needs: pip install tkcalendar

CREATE_NO_WINDOW = 0x08000000
# Make the application DPI aware
try:
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

# --- CONFIGURATION ---
# The command prefix uses 'wsl docker' to target the Docker daemon running inside WSL.
DOCKER_CMD_PREFIX = ["wsl", "docker"]
# --- END CONFIGURATION ---


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class WSLDockerMonitorApp(ttk.Frame):
    """
    A Tkinter application to monitor and manage Docker resources running inside WSL.
    Now includes automatic prerequisite checking and installation for WSL and Docker Engine.
    """

    def __init__(self, master=None):
        # Inherit from ttk.Frame and pass the master (main window)
        super().__init__(master)
        self.master.title("Nano Whale")
        self.master.geometry("900x700")
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        self.pack(fill="both", expand=True)

        # Stores references to active log processes/threads
        self.active_log_threads = []

        # Track prerequisite status
        self.prerequisites_checked = False
        self.prerequisites_ok = False

        # Create UI components
        self.create_status_panel()
        self.create_main_tabs()

        # Start prerequisite check in background
        self._start_prereq_check()

    def create_status_panel(self):
        """Create the status/log panel at the top"""
        status_frame = ttk.LabelFrame(self, text="System Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        self.status_text = scrolledtext.ScrolledText(
            status_frame,
            wrap=tk.WORD,
            height=8,
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 9),
        )
        self.status_text.pack(fill=tk.BOTH, expand=True)

        # Button frame for prerequisite actions
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

    def create_main_tabs(self):
        """Create the main notebook with tabs"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=(5, 10))

        # Initially disable tabs until prerequisites are met
        self.create_container_tab()
        self.create_image_tab()
        self.create_volume_tab()

    def log(self, message, level="INFO"):
        """Thread-safe logging to status window"""

        def update_log():
            timestamp = f"[{level}] "
            self.status_text.insert(tk.END, f"{timestamp}{message}\n")
            self.status_text.see(tk.END)
            self.status_text.update_idletasks()

        if self.status_text:
            self.master.after(0, update_log)

    def clear_log(self):
        """Clear the status log"""
        self.status_text.delete("1.0", tk.END)

    def on_close(self):
        """Clean up active log threads before closing and destroy the main window."""
        for thread in self.active_log_threads:
            if thread.is_alive() and thread.log_process:
                thread.log_process.terminate()
        self.master.destroy()
        sys.exit(0)

    # --- PREREQUISITE CHECKING AND INSTALLATION ---

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
            self.master.after(0, lambda: self.enable_docker_operations())
            self.master.after(0, self.refresh_all)
        else:
            self.log(
                "✗ Prerequisites not met. Please follow instructions above.", "ERROR"
            )
            self.master.after(0, lambda: self.disable_docker_operations())

        # Re-enable retry button
        self.master.after(0, lambda: self.retry_check_btn.config(state=tk.NORMAL))

    def check_prerequisites(self):
        """Check if WSL and Docker Engine are installed and working"""
        all_ok = True

        # Check 1: WSL 2
        self.log("Checking WSL 2 installation...", "INFO")
        wsl_ok = self._check_wsl()

        if not wsl_ok:
            self.log("✗ WSL 2 is not installed or not working", "ERROR")
            self.log("Attempting to install WSL 2...", "INSTALL")
            if self._install_wsl():
                # WSL installation requires reboot
                all_ok = False
                return all_ok
            else:
                all_ok = False
        else:
            self.log("✓ WSL 2 is installed and working", "SUCCESS")

        # Check 2: Docker Engine in WSL
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

                # Check if Docker daemon is running
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
        flags = 0

        # Only set the flag on Windows (nt)
        if os.name == "nt":
            # Set the flag to prevent the console window from showing
            flags = CREATE_NO_WINDOW
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
        try:
            flags = 0

            # Only set the flag on Windows (nt)
            if os.name == "nt":
                # Set the flag to prevent the console window from showing
                flags = CREATE_NO_WINDOW
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
        try:
            flags = 0

            # Only set the flag on Windows (nt)
            if os.name == "nt":
                # Set the flag to prevent the console window from showing
                flags = CREATE_NO_WINDOW
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
        try:
            flags = 0

            # Only set the flag on Windows (nt)
            if os.name == "nt":
                # Set the flag to prevent the console window from showing
                flags = CREATE_NO_WINDOW
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

                self.master.after(
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

        # Automated installation script
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

        # Escape quotes for command wrapper
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

            self.master.after(
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

            return False  # Indicates manual step required

        except Exception as e:
            self.log(f"Failed to launch installation: {e}", "ERROR")
            return False

    def enable_docker_operations(self):
        """Enable all Docker operation buttons"""
        # This method can be extended to enable/disable specific buttons
        pass

    def disable_docker_operations(self):
        """Disable Docker operation buttons when prerequisites aren't met"""
        pass

    # --- COMMAND EXECUTION ---

    def _execute_command(
        self,
        command_parts,
        success_message="Command executed successfully.",
        error_message="Error executing command.",
    ):
        """
        Executes a Docker command using the WSL prefix and handles subprocess output.
        Returns (success_bool, output_string).
        """
        if not self.prerequisites_ok:
            messagebox.showerror(
                "Prerequisites Not Met",
                "WSL and Docker Engine must be installed first.\n"
                "Please complete the prerequisite checks.",
            )
            return False, ""

        full_command = DOCKER_CMD_PREFIX + command_parts
        flags = 0
        if os.name == "nt":
            flags = CREATE_NO_WINDOW  # Use the defined constant
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

    def refresh_all(self):
        """Refreshes data in all tabs."""
        if self.prerequisites_ok:
            self.refresh_containers()
            self.refresh_images()
            self.refresh_volumes()

    def _get_selected_id(self, tree):
        """Retrieves the full ID (iid) of the selected item in a Treeview."""
        selected_item = tree.focus()
        if not selected_item:
            messagebox.showwarning(
                "Selection Required", "Please select a resource first."
            )
            return None
        return selected_item

    # --- CONTAINER TAB IMPLEMENTATION ---

    def create_container_tab(self):
        container_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(container_frame, text="Containers")

        # Treeview setup
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

        # Scrollbar
        vsb = ttk.Scrollbar(
            container_frame, orient="vertical", command=self.containers_tree.yview
        )
        vsb.pack(side="right", fill="y")

        self.containers_tree.configure(yscrollcommand=vsb.set)
        self.containers_tree.bind(
            "<Control-a>", lambda e: self.select_all(self.containers_tree)
        )
        # Button Frame
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
        """Fetches and displays the list of all containers (running and stopped)."""
        success, output = self._execute_command(
            ["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"],
            success_message="Containers refreshed.",
        )

        # Clear existing entries
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
        """Performs a start, stop, or restart action on selected container(s)."""
        selected_containers = self.containers_tree.selection()

        if not selected_containers:
            messagebox.showwarning(
                "Selection Required", "Please select container(s) first."
            )
            return

        # count = len(selected_containers)

        # Check restart policy before stopping (for multiple containers)
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

        # Perform action on all selected containers
        for container_id in selected_containers:
            self._execute_command(
                [action, container_id],
                success_message=f"Container {container_id[:12]} {action}ed successfully.",
                error_message=f"Failed to {action} container {container_id[:12]}.",
            )

        self.refresh_containers()

    def prune_containers(self):
        """Removes all stopped containers."""
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
        """
        Executes an interactive terminal (bash) in the selected container.
        """
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

    # --- IMAGE TAB IMPLEMENTATION ---

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
        """Select all items in a treeview."""
        tree.selection_set(tree.get_children())
        return "break"  # Prevent default behavior

    def refresh_images(self):
        """Fetches and displays the list of images."""
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
        """Removes selected image(s)."""
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
                ["rmi", "-f", image_id],  # Add -f flag to force removal
                success_message=f"Image {image_id[:12]} removed successfully.",
                error_message=f"Failed to remove image {image_id[:12]}.",
            )

        self.refresh_images()

    def prune_images(self):
        """Removes all dangling (unused) images."""
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

    # --- VOLUME TAB IMPLEMENTATION ---

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
        """Fetches and displays the list of volumes."""
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
        """Removes selected volume(s)."""
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

        if response is None:  # Cancel
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
        """Removes all unused volumes."""
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

    # --- LOGS IMPLEMENTATION ---

    def _get_wsl_current_time(self):
        """Fetches the current UTC time from WSL using the required format."""
        command = ["date", "-u", "+%Y-%m-%dT%H:%M:%S.%NZ"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error fetching WSL date: {e}")
            return None

    def _safe_remove_log_thread(self, thread_instance):
        """Safely removes a thread instance from the active list."""
        try:
            if thread_instance in self.active_log_threads:
                self.active_log_threads.remove(thread_instance)
        except Exception as e:
            # Log or print the error, but prevent the program crash
            print(
                f"Warning: Failed to safely remove thread {thread_instance.name}: {e}"
            )

    def _show_datetime_picker(self, master, target_var):
        """Opens a Toplevel window with a Calendar and time Spinboxes."""

        cal_window = tk.Toplevel(master)
        cal_window.title("Select Date and Time")
        cal_window.transient(master)

        # Variables for time
        hour_var = tk.IntVar(value=datetime.now().hour)
        minute_var = tk.IntVar(value=datetime.now().minute)
        second_var = tk.IntVar(value=datetime.now().second)

        # 1. Calendar Widget
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

        # 2. Time Input Frame
        time_frame = ttk.Frame(cal_window)
        time_frame.pack(pady=5, padx=10)

        # Hour Spinbox
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

        # Minute Spinbox
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

        # Second Spinbox
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
            # Get selected date (YYYY-MM-DD)
            selected_date_str = cal.get_date()

            # Format time with padding and ensure UTC/Zulu 'Z' suffix
            time_str = (
                f"{hour_var.get():02d}:"
                f"{minute_var.get():02d}:"
                f"{second_var.get():02d}.000000000Z"  # Add nanosecond precision and Z for RFC3339
            )

            # Combine into RFC3339 format
            new_timestamp = f"{selected_date_str}T{time_str}"

            target_var.set(new_timestamp)
            cal_window.destroy()

        ttk.Button(cal_window, text="Set Datetime", command=set_datetime).pack(pady=10)
        cal_window.grab_set()
        master.wait_window(cal_window)

    # --- LOGS IMPLEMENTATION ---
    def show_logs(self):
        """Opens a Toplevel window to stream and watch logs for a selected container."""
        container_id = self._get_selected_id(self.containers_tree)
        if not container_id:
            return

        container_name = self.containers_tree.item(container_id, "values")[1]

        log_window = tk.Toplevel(self)
        log_window.title(f"Logs: {container_name} ({container_id[:12]})")
        # log_window.iconbitmap("nano_whale.ico")
        # log_window.geometry(view_logs_size)

        # Set icon using resource_path
        try:
            icon_path = resource_path("nano_whale.ico")
            log_window.iconbitmap(icon_path)
        except:
            pass

        # Calculate window size after window creation
        log_window.update_idletasks()  # Force window initialization
        screen_width = log_window.winfo_screenwidth()
        screen_height = log_window.winfo_screenheight()
        window_width = screen_width // 2
        window_height = 800
        log_window.geometry(f"{window_width}x{window_height}")

        # Control Frame (sits at the top)
        control_frame = ttk.Frame(log_window)
        control_frame.pack(fill="x", padx=10, pady=5)

        # Text widget for logs
        log_text = scrolledtext.ScrolledText(
            log_window,
            wrap=tk.WORD,
            state=tk.NORMAL,
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 10),
        )
        log_text.pack(expand=True, fill="both", padx=10, pady=10)

        # --- Variables and Entry Fields ---
        from_time_var = tk.StringVar(value="")
        to_time_var = tk.StringVar(value="")

        # ⬅️ NEW: Checkbox Variable, default to True (checked/on)
        timestamp_var = tk.BooleanVar(value=True)

        # Add a checkbutton command that explicitly doesn't clear the display text
        ttk.Checkbutton(
            control_frame,
            text="Show Timestamps (-t)",
            variable=timestamp_var,
            # ⬅️ CHANGE: Use a new mode 'timestamp_toggle' which won't clear the text
            command=lambda: restart_log_stream(mode="timestamp_toggle"),
        ).pack(side=tk.LEFT, padx=10)

        # From Entry and Picker
        ttk.Label(control_frame, text="From (RFC3339):").pack(side=tk.LEFT, padx=5)
        from_entry = ttk.Entry(control_frame, textvariable=from_time_var, width=25)
        from_entry.pack(side=tk.LEFT, padx=1)
        ttk.Button(
            control_frame,
            text="📅🕓",  # ⬅️ Updated Button Text
            # ⬅️ Call the new datetime picker function
            command=lambda: self._show_datetime_picker(log_window, from_time_var),
        ).pack(side=tk.LEFT, padx=(0, 1))

        # To Entry and Picker
        ttk.Label(control_frame, text="To (RFC3339):").pack(side=tk.LEFT, padx=5)
        to_entry = ttk.Entry(control_frame, textvariable=to_time_var, width=25)
        to_entry.pack(side=tk.LEFT, padx=1)
        ttk.Button(
            control_frame,
            text="📅🕗",  # ⬅️ Updated Button Text
            # ⬅️ Call the new datetime picker function
            command=lambda: self._show_datetime_picker(log_window, to_time_var),
        ).pack(side=tk.LEFT, padx=(0, 1))

        # Apply Filter Button
        # Note: Ensure restart_log_stream is defined or accessible here
        ttk.Button(
            control_frame,
            text="Apply Range Filter",
            command=lambda: restart_log_stream(mode="range"),
        ).pack(side=tk.LEFT, padx=10)

        def thread_exit_callback(thread_instance):
            self._safe_remove_log_thread(thread_instance)

        # --- Core Log Stream Management Functions ---

        def restart_log_stream(mode="clear", since_time=None, until_time=None):
            """Stops the current stream and starts a new one based on the mode."""
            nonlocal log_thread

            # ⬅️ Capture the current timestamp state from the UI
            show_timestamps = timestamp_var.get()
            # 1. Stop the current stream
            log_thread.terminate()

            log_text.config(state=tk.NORMAL)
            log_text.delete("1.0", tk.END)  # ⬅️ WIPE SCREEN ONLY HERE
            log_text.config(state=tk.DISABLED)

            if mode == "range":
                since_time = from_time_var.get() if from_time_var.get() else None
                until_time = to_time_var.get() if to_time_var.get() else None

            elif mode == "history":
                since_time = None
                until_time = None

            elif mode == "clear":
                # These modes force a clear
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

            elif (
                mode == "timestamp_toggle"
            ):  # ⬅️ This mode should inherit previous filters but NOT clear
                # Inherit the previous filter settings
                since_time = log_thread.since_time
                until_time = log_thread.until_time

            else:
                # If we don't clear, insert a separator for clarity
                log_text.after(
                    0, log_text.insert, tk.END, "\n--- Stream format updated ---\n"
                )
                log_text.see(tk.END)

            # 3. Create and start the new thread
            new_log_thread = LogStreamer(
                container_id,
                log_text,
                # lambda: self.active_log_threads.remove(new_log_thread),
                lambda instance: thread_exit_callback(
                    new_log_thread
                ),  # ⬅️ Use the safe callback
                since_time=since_time,
                until_time=until_time,  # Pass new until_time to LogStreamer
                # ⬅️ PASS THE TIMESTAMP STATE
                show_timestamps=show_timestamps,
            )

            # 4. Update tracking and bindings
            try:
                self.active_log_threads.remove(log_thread)
            except ValueError:
                self._safe_remove_log_thread(log_thread)

            self.active_log_threads.append(new_log_thread)
            log_window.bind("<Destroy>", lambda e: new_log_thread.terminate())
            new_log_thread.start()

            # 5. Update reference and notify user
            # nonlocal log_thread
            log_thread = new_log_thread

        # Initial log thread setup (must happen after restart_log_stream definition)
        log_thread = LogStreamer(
            container_id,
            log_text,
            lambda instance: self._safe_remove_log_thread(instance),
            since_time=self._get_wsl_current_time(),  # Start from current time to avoid overload
            until_time=None,
            show_timestamps=timestamp_var.get(),  # ⬅️ Initial state
        )
        self.active_log_threads.append(log_thread)
        log_thread.start()

        # --- Bottom Button Frame ---
        button_frame = ttk.Frame(log_window)
        button_frame.pack(pady=5)

        # Option 2: All logs from start
        ttk.Button(
            button_frame,
            text="Show History",
            command=lambda: restart_log_stream(mode="history"),
        ).pack(side=tk.LEFT, padx=5)

        # General Clear Display Button (using current time, as requested)
        ttk.Button(
            button_frame,
            text="Clear",
            command=lambda: restart_log_stream(mode="clear"),
        ).pack(side=tk.LEFT, padx=(20, 5))

        ttk.Button(button_frame, text="Close", command=log_window.destroy).pack(
            side=tk.LEFT, padx=5
        )

        log_window.bind(
            "<Destroy>",
            lambda e: log_thread.terminate(),
        )


# --- LogStreamer Class Definition ---


class LogStreamer(threading.Thread):
    """A thread to stream Docker logs using subprocess.Popen."""

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
        self.show_timestamps = show_timestamps  # ⬅️ NEW: Store timestamp state
        self.log_process = None
        self.daemon = True
        self.running = True

    def run(self):
        command = DOCKER_CMD_PREFIX + ["logs"]

        # ⬅️ ADD -t FLAG CONDITIONALLY
        if self.show_timestamps:
            command.append("-t")

        # Only use -f (follow) if we are streaming indefinitely (no until filter)
        if not self.until_time:
            command.append("-f")

        if self.since_time:
            command.append(f"--since={self.since_time}")

        if self.until_time:
            command.append(f"--until={self.until_time}")  # ⬅️ New: Add --until

        command.append(self.container_id)

        # Example command (Range): ["docker", "logs", "--since=T1", "--until=T2", "id"]
        # Example command (Follow): ["docker", "logs", "-f", "id"]

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

            # If the log process stops naturally (i.e., when using --until)
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

    # append_text and terminate methods remain the same
    def append_text(self, content):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, content)
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)

    def terminate(self):
        self.running = False
        if self.log_process and self.log_process.poll() is None:
            self.log_process.terminate()


if __name__ == "__main__":
    # Check if running as Administrator (required for WSL installation)
    if os.name == "nt":
        try:
            is_admin = windll.shell32.IsUserAnAdmin()
            if not is_admin:
                print("WARNING: Not running as Administrator.")
                print("WSL installation will require Administrator privileges.")
        except:
            pass

    # Create root window FIRST before setting style
    root = tk.Tk()

    # 2. Get the screen dimensions in pixels
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # 3. Calculate the desired window dimensions
    # Half the screen width
    window_width = screen_width // 2
    # Keeping your requested height of 800 pixels
    window_height = 800

    # 4. Construct the geometry string in the format "WidthxHeight"
    view_logs_size = f"{window_width}x{window_height}"

    # Set theme for modern look
    style = ttk.Style()
    # root.iconbitmap("./nano_whale.ico")
    icon_path = resource_path("nano_whale.ico")
    root.iconbitmap(icon_path)

    try:
        style.theme_use("vista")  # Windows default
    except:
        style.theme_use("clam")  # Cross-platform fallback

    # root = tk.Tk()
    try:
        app = WSLDockerMonitorApp(master=root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror(
            "Application Error", f"The application failed to start: {e}"
        )
        root.destroy()
