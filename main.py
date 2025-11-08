import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import windll
from datetime import date, datetime
from tkinter import messagebox, scrolledtext

import tkcalendar as tkc  # Needs: pip install tkcalendar
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

CREATE_NO_WINDOW = 0x08000000
# Make the application DPI aware
try:
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

# --- CONFIGURATION ---
DOCKER_CMD_PREFIX = ["wsl", "docker"]
# --- END CONFIGURATION ---


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class WSLDockerMonitorApp(ttk.Frame):
    """
    A modern Tkinter application to monitor and manage Docker resources running inside WSL.
    """

    def __init__(self, master=None):
        super().__init__(master)
        self.master.title("🐋 Nano Whale - Docker Manager")
        self.master.geometry("1200x800")
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        self.pack(fill="both", expand=True)

        self.active_log_threads = []
        self.prerequisites_checked = False
        self.prerequisites_ok = False

        self.create_status_panel()
        self.create_main_tabs()
        self._start_prereq_check()

    def create_status_panel(self):
        """Create the status/log panel at the top with modern styling"""
        status_frame = ttk.Labelframe(
            self, text="  System Status", padding="15", bootstyle="primary"
        )
        status_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(15, 10))

        self.status_text = scrolledtext.ScrolledText(
            status_frame,
            wrap=tk.WORD,
            height=8,
            bg="#2b2b2b",
            fg="#e0e0e0",
            font=("Consolas", 10),
            relief="flat",
            borderwidth=0,
        )
        self.status_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Button frame
        button_frame = ttk.Frame(status_frame)
        button_frame.pack(fill=tk.X)

        self.retry_check_btn = ttk.Button(
            button_frame,
            text="🔄 Retry Prerequisites Check",
            command=self._start_prereq_check,
            state=tk.DISABLED,
            bootstyle="info",
            width=25,
        )
        self.retry_check_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="🗑️ Clear Log",
            command=self.clear_log,
            bootstyle="secondary",
            width=15,
        ).pack(side=tk.LEFT, padx=5)

    def create_main_tabs(self):
        """Create the main notebook with modern tabs"""
        self.notebook = ttk.Notebook(self, bootstyle="dark")
        self.notebook.pack(expand=True, fill="both", padx=15, pady=(10, 15))

        self.create_container_tab()
        self.create_image_tab()
        self.create_volume_tab()

    def log(self, message, level="INFO"):
        """Thread-safe logging with color coding"""

        def update_log():
            colors = {
                "INFO": "#4a9eff",
                "SUCCESS": "#00d084",
                "ERROR": "#ff4757",
                "WARNING": "#ffa502",
                "INSTALL": "#a29bfe",
                "FATAL": "#ff3838",
            }
            color = colors.get(level, "#e0e0e0")
            timestamp = f"[{level}] "

            self.status_text.tag_config(level, foreground=color)
            self.status_text.insert(tk.END, timestamp, level)
            self.status_text.insert(tk.END, f"{message}\n")
            self.status_text.see(tk.END)
            self.status_text.update_idletasks()

        if self.status_text:
            self.master.after(0, update_log)

    def clear_log(self):
        self.status_text.delete("1.0", tk.END)

    def on_close(self):
        for thread in self.active_log_threads:
            if thread.is_alive() and thread.log_process:
                thread.log_process.terminate()
        self.master.destroy()
        sys.exit(0)

    # --- PREREQUISITE CHECKING ---

    def _start_prereq_check(self):
        self.log("Starting prerequisite check...", "INFO")
        self.retry_check_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._check_prerequisites_threaded, daemon=True).start()

    def _check_prerequisites_threaded(self):
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

        self.master.after(0, lambda: self.retry_check_btn.config(state=tk.NORMAL))

    def check_prerequisites(self):
        all_ok = True
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
                self.master.after(
                    0,
                    lambda: messagebox.showerror(
                        "REBOOT REQUIRED",
                        "WSL installation requires a system reboot.\n\nPlease REBOOT YOUR COMPUTER NOW.",
                    ),
                )
                return True
            else:
                self.log(f"WSL installation failed: {result.stderr}", "ERROR")
                return False
        except Exception as e:
            self.log(f"WSL installation error: {e}", "ERROR")
            return False

    def _install_docker_engine(self):
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
            "echo 'Press Enter to close...';"
            "read;"
        )
        escaped_script = DOCKER_INSTALL_SCRIPT.replace('"', '\\"')
        command = f'start "" cmd /K wsl sh -c "{escaped_script}"'

        try:
            subprocess.Popen(command, shell=True)
            self.log("✓ Installation terminal launched", "SUCCESS")
            self.master.after(
                0,
                lambda: messagebox.showinfo(
                    "Manual Step Required",
                    "A terminal window has opened for Docker Engine installation.\n\n"
                    "Steps:\n1. Enter your WSL password\n2. Wait for completion\n"
                    "3. Click 'Retry Prerequisites Check'",
                ),
            )
            return False
        except Exception as e:
            self.log(f"Failed to launch installation: {e}", "ERROR")
            return False

    def enable_docker_operations(self):
        pass

    def disable_docker_operations(self):
        pass

    # --- COMMAND EXECUTION ---

    def _execute_command(
        self,
        command_parts,
        success_message="",
        error_message="Error executing command.",
    ):
        if not self.prerequisites_ok:
            messagebox.showerror(
                "Prerequisites Not Met",
                "WSL and Docker Engine must be installed first.",
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
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return False, str(e)

    def refresh_all(self):
        if self.prerequisites_ok:
            self.refresh_containers()
            self.refresh_images()
            self.refresh_volumes()

    def _get_selected_id(self, tree):
        selected_item = tree.focus()
        if not selected_item:
            messagebox.showwarning(
                "Selection Required", "Please select a resource first."
            )
            return None
        return selected_item

    # --- CONTAINER TAB ---

    def create_container_tab(self):
        container_frame = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(container_frame, text="🐳 Containers")

        # Header with info
        header = ttk.Frame(container_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            header, text="Container Management", font=("Segoe UI", 12, "bold")
        ).pack(side=tk.LEFT)

        # Treeview with modern styling
        columns = ("ID", "Name", "Image", "Status")
        self.containers_tree = ttk.Treeview(
            container_frame,
            columns=columns,
            show="headings",
            height=15,
            bootstyle="info",
        )
        self.containers_tree.pack(fill="both", expand=True, pady=(0, 10))

        for col in columns:
            self.containers_tree.heading(col, text=col, anchor=tk.W)

        self.containers_tree.column("ID", width=120)
        self.containers_tree.column("Name", width=200)
        self.containers_tree.column("Image", width=250)
        self.containers_tree.column("Status", width=180)

        vsb = ttk.Scrollbar(
            container_frame,
            orient="vertical",
            command=self.containers_tree.yview,
            bootstyle="info-round",
        )
        vsb.pack(side="right", fill="y")
        self.containers_tree.configure(yscrollcommand=vsb.set)

        # Button Frame
        button_frame = ttk.Frame(container_frame)
        button_frame.pack(pady=10)

        buttons = [
            ("🔄 Refresh", self.refresh_containers, "info"),
            ("▶️ Start", lambda: self.manage_container("start"), "success"),
            ("⏹️ Stop", lambda: self.manage_container("stop"), "danger"),
            ("🔄 Restart", lambda: self.manage_container("restart"), "warning"),
            ("📋 Logs", self.show_logs, "primary"),
            ("💻 Terminal", self.exec_terminal, "secondary"),
            ("🗑️ Prune", self.prune_containers, "danger"),
        ]

        for text, cmd, style in buttons:
            ttk.Button(
                button_frame, text=text, command=cmd, bootstyle=style, width=12
            ).pack(side=tk.LEFT, padx=3)

    def refresh_containers(self):
        success, output = self._execute_command(
            ["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"]
        )

        for item in self.containers_tree.get_children():
            self.containers_tree.delete(item)

        if success and output:
            for line in output.strip().split("\n"):
                if line:
                    try:
                        cid, name, image, status = line.split("\t", 3)
                        self.containers_tree.insert(
                            "", tk.END, values=(cid[:12], name, image, status), iid=cid
                        )
                    except ValueError:
                        pass

    def manage_container(self, action):
        container_id = self._get_selected_id(self.containers_tree)
        if not container_id:
            return
        success, _ = self._execute_command([action, container_id])
        if success:
            self.refresh_containers()

    def prune_containers(self):
        if not messagebox.askyesno("Confirm", "Remove ALL stopped containers?"):
            return
        success, output = self._execute_command(["container", "prune", "-f"])
        if success:
            messagebox.showinfo("Success", "Stopped containers removed!")
            self.refresh_containers()

    def exec_terminal(self):
        container_id = self._get_selected_id(self.containers_tree)
        if not container_id:
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
            messagebox.showerror("Error", f"Failed to open terminal: {e}")

    # --- IMAGE TAB ---

    def create_image_tab(self):
        image_frame = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(image_frame, text="📦 Images")

        header = ttk.Frame(image_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Image Management", font=("Segoe UI", 12, "bold")).pack(
            side=tk.LEFT
        )

        columns = ("ID", "Repository", "Tag", "Size")
        self.images_tree = ttk.Treeview(
            image_frame,
            columns=columns,
            show="headings",
            height=15,
            bootstyle="success",
        )
        self.images_tree.pack(fill="both", expand=True, pady=(0, 10))

        for col in columns:
            self.images_tree.heading(col, text=col, anchor=tk.W)
            self.images_tree.column(col, width=200)

        vsb = ttk.Scrollbar(
            image_frame,
            orient="vertical",
            command=self.images_tree.yview,
            bootstyle="success-round",
        )
        vsb.pack(side="right", fill="y")
        self.images_tree.configure(yscrollcommand=vsb.set)

        button_frame = ttk.Frame(image_frame)
        button_frame.pack(pady=10)

        buttons = [
            ("🔄 Refresh", self.refresh_images, "info"),
            ("🗑️ Remove", self.remove_image, "danger"),
            ("🧹 Prune Dangling", self.prune_images, "warning"),
        ]

        for text, cmd, style in buttons:
            ttk.Button(
                button_frame, text=text, command=cmd, bootstyle=style, width=18
            ).pack(side=tk.LEFT, padx=5)

    def refresh_images(self):
        success, output = self._execute_command(
            ["images", "--format", "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}"]
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
                        pass

    def remove_image(self):
        image_id = self._get_selected_id(self.images_tree)
        if not image_id:
            return
        if not messagebox.askyesno("Confirm", f"Remove image {image_id[:12]}?"):
            return
        success, _ = self._execute_command(["rmi", image_id])
        if success:
            self.refresh_images()

    def prune_images(self):
        if not messagebox.askyesno("Confirm", "Remove ALL dangling images?"):
            return
        success, output = self._execute_command(["image", "prune", "-f"])
        if success:
            messagebox.showinfo("Success", "Dangling images removed!")
            self.refresh_images()

    # --- VOLUME TAB ---

    def create_volume_tab(self):
        volume_frame = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(volume_frame, text="💾 Volumes")

        header = ttk.Frame(volume_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Volume Management", font=("Segoe UI", 12, "bold")).pack(
            side=tk.LEFT
        )

        columns = ("Name", "Driver")
        self.volumes_tree = ttk.Treeview(
            volume_frame,
            columns=columns,
            show="headings",
            height=15,
            bootstyle="warning",
        )
        self.volumes_tree.pack(fill="both", expand=True, pady=(0, 10))

        for col in columns:
            self.volumes_tree.heading(col, text=col, anchor=tk.W)
            self.volumes_tree.column(col, width=400)

        vsb = ttk.Scrollbar(
            volume_frame,
            orient="vertical",
            command=self.volumes_tree.yview,
            bootstyle="warning-round",
        )
        vsb.pack(side="right", fill="y")
        self.volumes_tree.configure(yscrollcommand=vsb.set)

        button_frame = ttk.Frame(volume_frame)
        button_frame.pack(pady=10)

        buttons = [
            ("🔄 Refresh", self.refresh_volumes, "info"),
            ("🗑️ Remove", self.remove_volume, "danger"),
            ("🧹 Prune Unused", self.prune_volumes, "warning"),
        ]

        for text, cmd, style in buttons:
            ttk.Button(
                button_frame, text=text, command=cmd, bootstyle=style, width=18
            ).pack(side=tk.LEFT, padx=5)

    def refresh_volumes(self):
        success, output = self._execute_command(
            ["volume", "ls", "--format", "{{.Name}}\t{{.Driver}}"]
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
                        pass

    def remove_volume(self):
        volume_name = self._get_selected_id(self.volumes_tree)
        if not volume_name:
            return
        if not messagebox.askyesno("Confirm", f"Remove volume {volume_name}?"):
            return
        success, _ = self._execute_command(["volume", "rm", volume_name])
        if success:
            self.refresh_volumes()

    def prune_volumes(self):
        if not messagebox.askyesno("Confirm", "Remove ALL unused volumes?"):
            return
        success, output = self._execute_command(["volume", "prune", "-f"])
        if success:
            messagebox.showinfo("Success", "Unused volumes removed!")
            self.refresh_volumes()

    # --- LOGS ---

    def _get_wsl_current_time(self):
        try:
            result = subprocess.run(
                ["date", "-u", "+%Y-%m-%dT%H:%M:%S.%NZ"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except:
            return None

    def _safe_remove_log_thread(self, thread_instance):
        try:
            if thread_instance in self.active_log_threads:
                self.active_log_threads.remove(thread_instance)
        except Exception as e:
            print(f"Warning: Failed to remove thread: {e}")

    def _show_datetime_picker(self, master, target_var):
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
            time_str = f"{hour_var.get():02d}:{minute_var.get():02d}:{second_var.get():02d}.000000000Z"
            new_timestamp = f"{selected_date_str}T{time_str}"
            target_var.set(new_timestamp)
            cal_window.destroy()

        ttk.Button(
            cal_window, text="Set Datetime", command=set_datetime, bootstyle="success"
        ).pack(pady=10)
        cal_window.grab_set()
        master.wait_window(cal_window)

    def show_logs(self):
        container_id = self._get_selected_id(self.containers_tree)
        if not container_id:
            return

        container_name = self.containers_tree.item(container_id, "values")[1]

        log_window = tk.Toplevel(self)
        log_window.title(f"📋 Logs: {container_name} ({container_id[:12]})")

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

        # Control Frame with modern styling
        control_frame = ttk.Labelframe(
            log_window, text="  Log Controls", padding="10", bootstyle="primary"
        )
        control_frame.pack(fill="x", padx=15, pady=10)

        log_text = scrolledtext.ScrolledText(
            log_window,
            wrap=tk.WORD,
            state=tk.NORMAL,
            bg="#1e1e1e",
            fg="#e0e0e0",
            font=("Consolas", 10),
            relief="flat",
            borderwidth=0,
        )
        log_text.pack(expand=True, fill="both", padx=15, pady=(0, 10))

        from_time_var = tk.StringVar(value="")
        to_time_var = tk.StringVar(value="")
        timestamp_var = tk.BooleanVar(value=True)

        # Top row - timestamp checkbox
        top_row = ttk.Frame(control_frame)
        top_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Checkbutton(
            top_row,
            text="🕒 Show Timestamps",
            variable=timestamp_var,
            bootstyle="primary-round-toggle",
            command=lambda: restart_log_stream(mode="timestamp_toggle"),
        ).pack(side=tk.LEFT, padx=5)

        # Middle row - date pickers
        date_row = ttk.Frame(control_frame)
        date_row.pack(fill=tk.X, pady=5)

        ttk.Label(date_row, text="From:").pack(side=tk.LEFT, padx=(5, 2))
        from_entry = ttk.Entry(date_row, textvariable=from_time_var, width=22)
        from_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(
            date_row,
            text="📅",
            width=3,
            command=lambda: self._show_datetime_picker(log_window, from_time_var),
            bootstyle="info",
        ).pack(side=tk.LEFT, padx=2)

        ttk.Label(date_row, text="To:").pack(side=tk.LEFT, padx=(10, 2))
        to_entry = ttk.Entry(date_row, textvariable=to_time_var, width=22)
        to_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(
            date_row,
            text="📅",
            width=3,
            command=lambda: self._show_datetime_picker(log_window, to_time_var),
            bootstyle="info",
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            date_row,
            text="Apply Range",
            command=lambda: restart_log_stream(mode="range"),
            bootstyle="success",
            width=12,
        ).pack(side=tk.LEFT, padx=(10, 5))

        def thread_exit_callback(thread_instance):
            self._safe_remove_log_thread(thread_instance)

        log_thread = LogStreamer(
            container_id,
            log_text,
            lambda instance: thread_exit_callback(instance),
            since_time=None,
            until_time=None,
            show_timestamps=timestamp_var.get(),
        )
        self.active_log_threads.append(log_thread)
        log_thread.start()

        def restart_log_stream(mode="clear", since_time=None, until_time=None):
            nonlocal log_thread
            show_timestamps = timestamp_var.get()
            log_thread.terminate()

            clear_required = mode in ("clear", "start", "range")

            if clear_required:
                log_text.config(state=tk.NORMAL)
                log_text.delete("1.0", tk.END)
                log_text.config(state=tk.DISABLED)

            log_message = ""

            if mode == "range":
                since_time = from_time_var.get() if from_time_var.get() else None
                until_time = to_time_var.get() if to_time_var.get() else None
                log_message = f"--- Streaming log range: FROM {since_time or 'START'} TO {until_time or 'NOW'} ---"

            elif mode == "start":
                since_time = None
                until_time = None
                log_message = (
                    "--- Streaming ALL available logs from container start ---"
                )

            elif mode == "clear" or mode == "current":
                since_time = self._get_wsl_current_time()
                until_time = None
                if not since_time:
                    log_text.after(
                        0,
                        log_text.insert,
                        tk.END,
                        "--- ERROR: Could not fetch time ---\n",
                    )
                    return
                log_message = f"--- Streaming from current moment: {since_time} ---"

            elif mode == "timestamp_toggle":
                since_time = log_thread.since_time
                until_time = log_thread.until_time
                log_message = (
                    f"--- Timestamps are now {'ON' if show_timestamps else 'OFF'} ---"
                )

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

            if not clear_required:
                log_text.config(state=tk.NORMAL)
                log_text.insert(tk.END, "\n" + "=" * 50 + "\n")

            log_text.after(
                0, log_text.insert, tk.END, "\n======== NEW STREAM STARTED ========\n"
            )
            log_text.after(0, log_text.insert, tk.END, log_message + "\n")
            log_text.see(tk.END)

        # Bottom button frame with modern styling
        button_frame = ttk.Frame(log_window)
        button_frame.pack(pady=10, padx=15)

        buttons = [
            ("📜 All Logs", lambda: restart_log_stream(mode="start"), "info"),
            (
                "▶️ Stream from Now",
                lambda: restart_log_stream(mode="current"),
                "success",
            ),
            ("🔄 Clear & Restart", lambda: restart_log_stream(mode="clear"), "warning"),
            ("❌ Close", log_window.destroy, "danger"),
        ]

        for text, cmd, style in buttons:
            ttk.Button(
                button_frame, text=text, command=cmd, bootstyle=style, width=18
            ).pack(side=tk.LEFT, padx=3)

        log_window.bind("<Destroy>", lambda e: log_thread.terminate())


class LogStreamer(threading.Thread):
    """A thread to stream Docker logs"""

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
                    f"\n--- Log stream finished at {self.until_time} ---\n",
                )

        except Exception as e:
            self.text_widget.after(0, self.append_text, f"\n--- ERROR: {e} ---\n")
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


if __name__ == "__main__":
    if os.name == "nt":
        try:
            is_admin = windll.shell32.IsUserAnAdmin()
            if not is_admin:
                print("WARNING: Not running as Administrator.")
        except:
            pass

    # Create root with ttkbootstrap theme
    root = ttk.Window(themename="darkly")  # Modern dark theme
    root.title("🐋 Nano Whale - Docker Manager")

    # Set icon
    try:
        icon_path = resource_path("nano_whale.ico")
        root.iconbitmap(icon_path)
    except Exception as e:
        print(f"Could not set icon: {e}")

    try:
        app = WSLDockerMonitorApp(master=root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Application Error", f"Failed to start: {e}")
        root.destroy()
