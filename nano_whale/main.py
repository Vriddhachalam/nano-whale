import subprocess
import time
import platform
import shutil
import os
import json
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, TabbedContent, TabPane
from textual.containers import Container, ScrollableContainer
from typing import Literal
from textual.binding import Binding
from textual.events import Focus, Click


def get_platform() -> str:
    """Detect the current platform."""
    system = platform.system().lower()
    if system == "windows":
        # Check if WSL is available
        if shutil.which("wsl"):
            return "windows_wsl"
        return "windows"
    elif system == "linux":
        return "linux"
    elif system == "darwin":
        return "macos"
    return "unknown"


PLATFORM = get_platform()


def run_docker_command(command_parts: list[str]) -> tuple[int, str]:
    """Executes a docker command based on platform."""
    if PLATFORM == "windows_wsl":
        full_command = ["wsl", "docker"] + command_parts
    else:
        full_command = ["docker"] + command_parts
    
    try:
        result = subprocess.run(full_command, capture_output=True, text=True, check=False)
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        if PLATFORM == "windows_wsl":
            return 1, "Error: 'wsl' not found."
        else:
            return 1, "Error: 'docker' not found."
    except Exception as e:
        return 1, str(e)


class DockerTUI(App[None]):
    """Fast TUI for Docker."""
    
    mode: Literal["CONTAINERS", "IMAGES", "VOLUMES"] = "CONTAINERS"
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("a", "refresh", "Refresh", show=True),
        Binding("g", "toggle_stats", "Stats ON/OFF", show=True),
        Binding("r", "restart_container", "Restart", show=True),
        Binding("x", "stop_container", "Stop", show=True),
        Binding("s", "start_container", "Start", show=True),
        Binding("l", "watch_logs", "Logs (in-shell)", show=True),
        Binding("ctrl+l", "watch_logs_new_terminal", "Logs (new)", show=True),
        Binding("d", "delete_item", "Delete", show=True),
        Binding("p", "show_prune_menu", "Prune", show=True),
        Binding("c", "switch_table('CONTAINERS')", "Containers", show=True),
        Binding("i", "switch_table('IMAGES')", "Images", show=True),
        Binding("v", "switch_table('VOLUMES')", "Volumes", show=True),
        Binding("m", "toggle_multi_select", "Mark", show=True),
        Binding("t", "launch_terminal", "Terminal (in-shell)", show=True),
        Binding("ctrl+t", "launch_terminal_new", "Terminal (new)", show=True),
        Binding("1", "switch_detail_tab('tab-info')", "Info", show=True),
        Binding("2", "switch_detail_tab('tab-env')", "Env", show=True),
        Binding("3", "switch_detail_tab('tab-ports')", "Ports", show=True),
        Binding("4", "switch_detail_tab('tab-volumes')", "Volumes", show=True),
        Binding("5", "switch_detail_tab('tab-networks')", "Networks", show=True),


    ]
    
    CSS = """
    #main-container {
        height: 100%;
        layout: grid;
        grid-size: 2 2;
        grid-columns: 40% 60%;
        grid-rows: 85% 15%;
    }
    
    #tables-panel {
        row-span: 50;
        height: 100%;
        border: heavy green;
        layout: vertical;
    }
    
    .table-section {
        height: 1fr;
        border: none;
    }
    
    .table-label {
        height: 1;
        background: $surface;
        color: $text-muted;
        text-style: bold;
        padding: 0 1;
    }
    
    .table-label-focused {
        background: $accent;
        color: $text;
    }
    
    #containers-table, #images-table, #volumes-table {
        height: 1fr;
    }
    
    /* Keep table highlighted even when not focused */
    DataTable:focus {
        border: tall $accent;
    }
    
    DataTable {
        border: tall $accent 50%;
    }
    
    #preview-panel {
        height: 100%;
        border: heavy cyan;
    }
    
    TabPane {
        padding: 0;
    }
    
    #info-content, #env-content, #ports-content, #volumes-content, #networks-content {
        width: 100%;
        height: 100%;
        border: none;
    }
    
    #log-panel {
        height: 100%;
        border: heavy white;
        padding: 1;
        overflow-y: auto;
        color: #ADFF2F;
    }
    """
    
    def __init__(self):
        super().__init__()
        self._prune_ready = False
        self._prune_timer = None
        self._selected_items = []
        self._multi_select_mode = False
        self.selected_row_data = None
        self._show_stats = False
        self._stats_cache = {}
        self._stats_cache_time = 0
        self._cache_ttl = 2.0
        self._details_cache = {}
        self._current_container_id = None
    
    def _get_current_table(self) -> DataTable | None:
        """Safely get the current active table."""
        try:
            if self.mode == "CONTAINERS":
                return self.query_one("#containers-table", DataTable)
            elif self.mode == "IMAGES":
                return self.query_one("#images-table", DataTable)
            else:
                return self.query_one("#volumes-table", DataTable)
        except:
            return None
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Container(id="tables-panel"):
                with Container(id="containers-section", classes="table-section"):
                    yield Static("Containers (c)", id="containers-label", classes="table-label")
                    yield DataTable(id="containers-table")
                with Container(id="images-section", classes="table-section"):
                    yield Static("Images (i)", id="images-label", classes="table-label")
                    yield DataTable(id="images-table")
                with Container(id="volumes-section", classes="table-section"):
                    yield Static("Volumes (v)", id="volumes-label", classes="table-label")
                    yield DataTable(id="volumes-table")
            with TabbedContent(id="preview-panel"):
                with TabPane("Info (1)", id="tab-info"):
                    with ScrollableContainer():
                        yield Static("Select a container", id="info-content", markup=True)
                with TabPane("Env (2)", id="tab-env"):
                    with ScrollableContainer():
                        yield Static("", id="env-content", markup=True)
                with TabPane("Ports (3)", id="tab-ports"):
                    with ScrollableContainer():
                        yield Static("", id="ports-content", markup=True)
                with TabPane("Volumes (4)", id="tab-volumes"):
                    with ScrollableContainer():
                        yield Static("", id="volumes-content", markup=True)
                with TabPane("Networks (5)", id="tab-networks"):
                    with ScrollableContainer():
                        yield Static("", id="networks-content", markup=True)
            yield Static("Ready.", id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#log-panel", Static).markup = False
        
        # Setup all tables
        for table_id in ["containers-table", "images-table", "volumes-table"]:
            table = self.query_one(f"#{table_id}", DataTable)
            table.cursor_type = "row"
        
        platform_name = {
            "windows_wsl": "Windows (WSL)",
            "linux": "Linux",
            "macos": "macOS",
            "windows": "Windows (native)",
            "unknown": "Unknown"
        }.get(PLATFORM, "Unknown")
        self.notify(f"Platform: {platform_name}", severity="information", timeout=2)
        
        # Populate all tables on mount
        self._populate_all_tables()
        
        # Highlight containers label and focus the containers table by default
        self._update_table_labels()
        
        # Use set_timer to ensure focus happens after full render
        self.set_timer(0.1, self._focus_containers_table)
    
    def _focus_containers_table(self) -> None:
        """Focus containers table after app is fully rendered."""
        try:
            self.mode = "CONTAINERS"
            self._update_table_labels()
            container_table = self.query_one("#containers-table", DataTable)
            if container_table:
                container_table.focus()
                # Preload right pane for first container
                self.call_after_refresh(self._preload_first_container_preview)
        except Exception as e:
            self.append_to_log(f"Focus error: {e}")
    
    def _preload_first_container_preview(self) -> None:
        """Preload the preview panel for the first container on app launch."""
        try:
            table = self.query_one("#containers-table", DataTable)
            if table and table.row_count > 0:
                # Get first row data
                cell_key = table.coordinate_to_cell_key((0, 0))
                if cell_key and cell_key.row_key:
                    self.selected_row_data = list(table.get_row(cell_key.row_key))
                    self.append_to_log(f"📦 Preloading preview for first container")
                    self._update_preview_panel()
        except Exception as e:
            self.append_to_log(f"❌ Error preloading preview: {e}")
    
    def _populate_all_tables(self) -> None:
        """Populate all tables on app start."""
        # Populate containers
        self.mode = "CONTAINERS"
        self._update_single_table()
        
        # Populate images
        self.mode = "IMAGES"
        self._update_single_table()
        
        # Populate volumes
        self.mode = "VOLUMES"
        self._update_single_table()
        
        # Set mode back to CONTAINERS as default
        self.mode = "CONTAINERS"
    
    def action_toggle_stats(self) -> None:
        """Toggle stats display for containers."""
        self._show_stats = not self._show_stats
        status = "ON" if self._show_stats else "OFF"
        self.notify(f"Stats display: {status}", severity="information")
        if self.mode == "CONTAINERS":
            self.update_data_list()
    
    def action_switch_table(self, new_mode: str) -> None:
        """Switch between Containers, Images, and Volumes tables."""
        self.mode = new_mode
        self._details_cache.clear()
        self._current_container_id = None
        
        # Update label highlighting and focus the appropriate table
        self._update_table_labels()
        
        if new_mode == "CONTAINERS":
            try:
                self.query_one("#containers-table", DataTable).focus()
            except Exception as e:
                self.append_to_log(f"Focus error: {e}")
        elif new_mode == "IMAGES":
            self.query_one("#images-table", DataTable).focus()
        elif new_mode == "VOLUMES":
            self.query_one("#volumes-table", DataTable).focus()
        
        self.update_data_list()
        self.notify(f"Switched to {self.mode}", severity="information", timeout=1)
    
    def _update_table_labels(self) -> None:
        """Update table label styling based on current mode."""
        try:
            containers_label = self.query_one("#containers-label", Static)
            images_label = self.query_one("#images-label", Static)
            volumes_label = self.query_one("#volumes-label", Static)
            
            # Remove focused class from all
            containers_label.remove_class("table-label-focused")
            images_label.remove_class("table-label-focused")
            volumes_label.remove_class("table-label-focused")
            
            # Add focused class to active one
            if self.mode == "CONTAINERS":
                containers_label.add_class("table-label-focused")
            elif self.mode == "IMAGES":
                images_label.add_class("table-label-focused")
            elif self.mode == "VOLUMES":
                volumes_label.add_class("table-label-focused")
        except:
            pass
    
    def action_switch_detail_tab(self, tab_id: str) -> None:
        """Switch between detail tabs (Info, Env, Ports, Volumes, Networks)."""
        preview_panel = self.query_one("#preview-panel", TabbedContent)
        preview_panel.active = tab_id
                
    def action_refresh(self) -> None:
        self._stats_cache.clear()
        self._details_cache.clear()
        self._current_container_id = None
        self.update_data_list()
        self.notify(f"{self.mode} refreshed.", severity="information", timeout=1)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.append_to_log(f"🎯 Row highlighted event: row_key={event.row_key}")
        try:
            if event.row_key:
                # Detect which table triggered the event and switch mode
                highlighted_table = event.data_table
                if highlighted_table.id == "containers-table":
                    if self.mode != "CONTAINERS":
                        self.mode = "CONTAINERS"
                        self._update_table_labels()
                elif highlighted_table.id == "images-table":
                    if self.mode != "IMAGES":
                        self.mode = "IMAGES"
                        self._update_table_labels()
                elif highlighted_table.id == "volumes-table":
                    if self.mode != "VOLUMES":
                        self.mode = "VOLUMES"
                        self._update_table_labels()
                
                self.selected_row_data = list(highlighted_table.get_row(event.row_key))
                self.append_to_log(f"✅ Got highlighted row data: {self.selected_row_data[:3]}...")
            else:
                self.selected_row_data = None
                self.append_to_log(f"⚠️ No row_key in event")
            self._update_preview_panel()
        except Exception as e:
            self.append_to_log(f"❌ Error in row_highlighted: {e}")
            self.selected_row_data = None
            self._update_preview_panel()
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection via mouse click."""
        self.append_to_log(f"🖱️ Row selected (click) event: row_key={event.row_key}")
        try:
            if event.row_key:
                # Detect which table was clicked and switch mode
                clicked_table = event.data_table
                if clicked_table.id == "containers-table":
                    if self.mode != "CONTAINERS":
                        self.mode = "CONTAINERS"
                        self._update_table_labels()
                elif clicked_table.id == "images-table":
                    if self.mode != "IMAGES":
                        self.mode = "IMAGES"
                        self._update_table_labels()
                elif clicked_table.id == "volumes-table":
                    if self.mode != "VOLUMES":
                        self.mode = "VOLUMES"
                        self._update_table_labels()
                
                self.selected_row_data = list(clicked_table.get_row(event.row_key))
                self.append_to_log(f"✅ Got selected row data: {self.selected_row_data[:3]}...")
                self._update_preview_panel()
            else:
                self.append_to_log(f"⚠️ No row_key in selection")
        except Exception as e:
            self.append_to_log(f"❌ Error in row_selected: {e}")
    
    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle cell selection via mouse click."""
        self.append_to_log(f"🖱️ Cell selected (click) event: row_key={event.cell_key.row_key}")
        try:
            if event.cell_key and event.cell_key.row_key:
                # Detect which table was clicked and switch mode
                clicked_table = event.data_table
                if clicked_table.id == "containers-table":
                    if self.mode != "CONTAINERS":
                        self.mode = "CONTAINERS"
                        self._update_table_labels()
                elif clicked_table.id == "images-table":
                    if self.mode != "IMAGES":
                        self.mode = "IMAGES"
                        self._update_table_labels()
                elif clicked_table.id == "volumes-table":
                    if self.mode != "VOLUMES":
                        self.mode = "VOLUMES"
                        self._update_table_labels()
                
                self.selected_row_data = list(clicked_table.get_row(event.cell_key.row_key))
                self.append_to_log(f"✅ Got cell row data: {self.selected_row_data[:3]}...")
                self._update_preview_panel()
            else:
                self.append_to_log(f"⚠️ No row_key in cell selection")
        except Exception as e:
            self.append_to_log(f"❌ Error in cell_selected: {e}")
    
    def on_click(self, event: Click) -> None:
        """Handle click anywhere - switch mode when clicking on table section."""
        try:
            # Walk up the widget tree to find if we clicked in a table section
            widget = event.widget
            while widget is not None:
                if hasattr(widget, 'id') and widget.id in ("containers-section", "containers-table", "containers-label"):
                    if self.mode != "CONTAINERS":
                        self.mode = "CONTAINERS"
                        self._update_table_labels()
                        self.query_one("#containers-table", DataTable).focus()
                        self.append_to_log(f"🖱️ Switched to CONTAINERS via click")
                    break
                elif hasattr(widget, 'id') and widget.id in ("images-section", "images-table", "images-label"):
                    if self.mode != "IMAGES":
                        self.mode = "IMAGES"
                        self._update_table_labels()
                        self.query_one("#images-table", DataTable).focus()
                        self.append_to_log(f"🖱️ Switched to IMAGES via click")
                    break
                elif hasattr(widget, 'id') and widget.id in ("volumes-section", "volumes-table", "volumes-label"):
                    if self.mode != "VOLUMES":
                        self.mode = "VOLUMES"
                        self._update_table_labels()
                        self.query_one("#volumes-table", DataTable).focus()
                        self.append_to_log(f"🖱️ Switched to VOLUMES via click")
                    break
                widget = widget.parent
        except Exception as e:
            self.append_to_log(f"❌ Error in click handler: {e}")
    
    def on_key(self, event) -> None:
        """Update preview when arrow keys are pressed."""
        if event.key in ["up", "down", "pageup", "pagedown", "home", "end"]:
            # Debounce: Let the event propagate to the table first
            self.set_timer(0.1, self._sync_preview_with_cursor)
    
    def _sync_preview_with_cursor(self) -> None:
        """Sync preview panel with current cursor position."""
        try:
            # Get the current active table
            # if self.mode == "CONTAINERS":
            #     table = self.query_one("#containers-table", DataTable)
            # elif self.mode == "IMAGES":
            #     table = self.query_one("#images-table", DataTable)
            # else:
            #     table = self.query_one("#volumes-table", DataTable)
            table = self._get_current_table()
            if not table:
                return
            
            self.append_to_log(f"🔄 Sync cursor: row={table.cursor_row}, count={table.row_count}")
            if table.cursor_row is not None and table.row_count > 0:
                cell_key = table.coordinate_to_cell_key((table.cursor_row, 0))
                if cell_key and cell_key.row_key:
                    self.selected_row_data = list(table.get_row(cell_key.row_key))
                    self.append_to_log(f"✅ Synced row data: {self.selected_row_data[:3]}...")
                    self._update_preview_panel()
                else:
                    self.append_to_log(f"❌ No cell_key or row_key in sync")
        except Exception as e:
            self.append_to_log(f"❌ Error in sync: {e}")
    
    def _update_preview_panel(self) -> None:
        """Update the preview panel with selected container details."""
        self.append_to_log(f"📊 Update preview called, selected_row_data: {bool(self.selected_row_data)}")
        
        if not self.selected_row_data:
            self.query_one("#info-content", Static).update("[dim]Select a container to view details[/dim]")
            return
            
        if self.mode != "CONTAINERS":
            self.query_one("#info-content", Static).update("[dim]Preview only available for containers[/dim]")
            return
        
        try:
            # Get the current active table
            # if self.mode == "CONTAINERS":
            #     table = self.query_one("#containers-table", DataTable)
            # elif self.mode == "IMAGES":
            #     table = self.query_one("#images-table", DataTable)
            # else:
            #     table = self.query_one("#volumes-table", DataTable)
            table = self._get_current_table()
            if not table:
                return
            col_labels = [str(col.label) for col in table.columns.values()]
            
            self.append_to_log(f"🔍 Column labels: {col_labels}")
            
            # Get container ID - account for MARK column
            if 'ID' in col_labels:
                id_idx = col_labels.index('ID')
                cid = self.selected_row_data[id_idx]
                self.append_to_log(f"✅ Container ID found: {cid}")
            else:
                self.append_to_log(f"❌ ID column not found in labels")
                self.query_one("#info-content", Static).update("Cannot find container ID")
                return
            
            # Check cache
            if cid == self._current_container_id and cid in self._details_cache:
                self.append_to_log(f"💾 Using cached data for {cid}")
                self._populate_tabs(self._details_cache[cid])
                return
            
            # Get container inspect data (only if changed)
            self.append_to_log(f"🔄 Fetching inspect data for {cid}")
            code, output = run_docker_command(["inspect", cid])
            if code != 0:
                self.append_to_log(f"❌ Inspect failed: {output[:100]}")
                self.query_one("#info-content", Static).update(f"Error inspecting container:\n{output}")
                return
            
            try:
                data = json.loads(output)[0]
                self.append_to_log(f"✅ Parsed inspect data successfully")
            except Exception as e:
                self.append_to_log(f"❌ JSON parse error: {e}")
                self.query_one("#info-content", Static).update("Error parsing container data")
                return
            
            # Cache the data
            self._current_container_id = cid
            self._details_cache[cid] = data
            
            # Populate tabs
            self.append_to_log(f"📝 Populating tabs for {cid}")
            self._populate_tabs(data)
            
        except Exception as e:
            self.query_one("#info-content", Static).update(f"Error updating preview:\n{str(e)}")
    
    def _populate_tabs(self, data) -> None:
        """Populate all tabs with container data."""
        try:
            cid = data.get('Id', '')[:12]
            self.append_to_log(f"🎨 Populating tabs for container {cid}")
            
            # INFO TAB
            try:
                info_content = []
                info_content.append(f"[bold cyan]Container: {data.get('Name', '').lstrip('/')}[/bold cyan]")
                info_content.append(f"[bold]ID:[/bold] {cid}")
                info_content.append(f"[bold]Full ID:[/bold] {data.get('Id', 'N/A')}")
                info_content.append(f"[bold]Image:[/bold] {data.get('Config', {}).get('Image', 'N/A')}")
                info_content.append(f"[bold]Image ID:[/bold] {data.get('Image', 'N/A')[:19]}")
                info_content.append(f"[bold]Status:[/bold] {data.get('State', {}).get('Status', 'N/A')}")
                info_content.append(f"[bold]Running:[/bold] {data.get('State', {}).get('Running', False)}")
                info_content.append(f"[bold]Paused:[/bold] {data.get('State', {}).get('Paused', False)}")
                info_content.append(f"[bold]Restarting:[/bold] {data.get('State', {}).get('Restarting', False)}")
                info_content.append(f"[bold]OOMKilled:[/bold] {data.get('State', {}).get('OOMKilled', False)}")
                info_content.append(f"[bold]Pid:[/bold] {data.get('State', {}).get('Pid', 0)}")
                info_content.append(f"[bold]Exit Code:[/bold] {data.get('State', {}).get('ExitCode', 0)}")
                info_content.append(f"[bold]Started:[/bold] {data.get('State', {}).get('StartedAt', 'N/A')}")
                info_content.append(f"[bold]Finished:[/bold] {data.get('State', {}).get('FinishedAt', 'N/A')}")
                info_content.append(f"[bold]Platform:[/bold] {data.get('Platform', 'N/A')}")
                info_content.append(f"[bold]Hostname:[/bold] {data.get('Config', {}).get('Hostname', 'N/A')}")
                info_content.append(f"[bold]Restart Policy:[/bold] {data.get('HostConfig', {}).get('RestartPolicy', {}).get('Name', 'N/A')}")
                self.query_one("#info-content", Static).update("\n".join(info_content))
                self.append_to_log(f"✅ Info tab updated")
            except Exception as e:
                self.append_to_log(f"❌ Error updating info tab: {e}")
        
            # ENV TAB
            try:
                env_vars = data.get('Config', {}).get('Env', [])
                env_content = []
                if env_vars:
                    env_content.append(f"[bold yellow]Environment Variables ({len(env_vars)}):[/bold yellow]\n")
                    for env in env_vars:
                        env_content.append(f"{env}")
                else:
                    env_content.append("[dim]No environment variables[/dim]")
                self.query_one("#env-content", Static).update("\n".join(env_content))
                self.append_to_log(f"✅ Env tab updated")
            except Exception as e:
                self.append_to_log(f"❌ Error updating env tab: {e}")
        
            # PORTS TAB
            try:
                ports = data.get('NetworkSettings', {}).get('Ports', {})
                ports_content = []
                if ports:
                    ports_content.append(f"[bold green]Port Mappings:[/bold green]\n")
                    for container_port, host_bindings in ports.items():
                        if host_bindings:
                            for binding in host_bindings:
                                host_ip = binding.get('HostIp', '0.0.0.0')
                                host_port = binding.get('HostPort', '?')
                                ports_content.append(f"[green]{host_ip}:{host_port}[/green] → [cyan]{container_port}[/cyan]")
                        else:
                            ports_content.append(f"[dim]{container_port} (not published)[/dim]")
                else:
                    ports_content.append("[dim]No port mappings[/dim]")
                self.query_one("#ports-content", Static).update("\n".join(ports_content))
                self.append_to_log(f"✅ Ports tab updated")
            except Exception as e:
                self.append_to_log(f"❌ Error updating ports tab: {e}")
        
            # VOLUMES TAB
            try:
                mounts = data.get('Mounts', [])
                volumes_content = []
                if mounts:
                    volumes_content.append(f"[bold magenta]Volumes ({len(mounts)}):[/bold magenta]\n")
                    for mount in mounts:
                        mount_type = mount.get('Type', 'N/A')
                        source = mount.get('Source', 'N/A')
                        dest = mount.get('Destination', 'N/A')
                        mode = mount.get('Mode', '')
                        rw = mount.get('RW', True)
                        volumes_content.append(f"[bold]Type:[/bold] {mount_type}")
                        volumes_content.append(f"[bold]Source:[/bold] {source}")
                        volumes_content.append(f"[bold]Destination:[/bold] {dest}")
                        volumes_content.append(f"[bold]Mode:[/bold] {mode} ({'RW' if rw else 'RO'})")
                        volumes_content.append("")
                else:
                    volumes_content.append("[dim]No volumes[/dim]")
                self.query_one("#volumes-content", Static).update("\n".join(volumes_content))
                self.append_to_log(f"✅ Volumes tab updated")
            except Exception as e:
                self.append_to_log(f"❌ Error updating volumes tab: {e}")
        
            # NETWORKS TAB
            try:
                networks = data.get('NetworkSettings', {}).get('Networks', {})
                networks_content = []
                if networks:
                    networks_content.append(f"[bold blue]Networks ({len(networks)}):[/bold blue]\n")
                    for net_name, net_data in networks.items():
                        networks_content.append(f"[bold cyan]{net_name}[/bold cyan]")
                        networks_content.append(f"  [bold]IP Address:[/bold] {net_data.get('IPAddress', 'N/A')}")
                        networks_content.append(f"  [bold]Gateway:[/bold] {net_data.get('Gateway', 'N/A')}")
                        networks_content.append(f"  [bold]MAC Address:[/bold] {net_data.get('MacAddress', 'N/A')}")
                        networks_content.append(f"  [bold]Network ID:[/bold] {net_data.get('NetworkID', 'N/A')[:12]}")
                        networks_content.append("")
                else:
                    networks_content.append("[dim]No networks[/dim]")
                self.query_one("#networks-content", Static).update("\n".join(networks_content))
                self.append_to_log(f"✅ Networks tab updated")
            except Exception as e:
                self.append_to_log(f"❌ Error updating networks tab: {e}")
                
        except Exception as e:
            self.append_to_log(f"❌ Fatal error in _populate_tabs: {e}")

    def _update_single_table(self) -> None:
        """Fast data update with optional stats."""
        # Get the current active table based on mode
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return
        output_widget = self.query_one("#log-panel", Static)
        
        if self.mode == "CONTAINERS":
            if self._show_stats:
                columns = ("MARK", "ID", "Names", "Image", "Status", "CPU%", "Mem%")
                command = ["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"]
            else:
                columns = ("MARK", "ID", "Names", "Image", "Status")
                command = ["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"]
            item_count = 4
        elif self.mode == "IMAGES":
            columns = ("MARK", "ID", "Repository", "Tag", "Size")
            command = ["image", "ls", "--format", "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}"]
            item_count = 4
        else:
            columns = ("MARK", "Name", "Driver")
            command = ["volume", "ls", "--format", "{{.Name}}\t{{.Driver}}"]
            item_count = 2

        table.clear()
        for col_key in list(table.columns.keys()):
            try:
                table.remove_column(col_key)
            except:
                pass
    
        try:
            table.add_columns(*columns)
        except Exception as e:
            self.notify(f"Column error: {e}", severity="error")
            return
            
        exit_code, output = run_docker_command(command)
        if exit_code != 0:
            output_widget.update(output)
            return
    
        lines = output.split('\n')
        marked_ids = [item[0] for item in self._selected_items] if self._multi_select_mode else []
        
        stats_data = {}
        if self.mode == "CONTAINERS" and self._show_stats:
            current_time = time.time()
            if current_time - self._stats_cache_time > self._cache_ttl or not self._stats_cache:
                running_ids = []
                for line in lines:
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 4 and 'up' in parts[3].lower():
                            running_ids.append(parts[0][:12])
                
                if running_ids:
                    stats_cmd = ["stats", "--no-stream", "--format", "{{.ID}}\t{{.CPUPerc}}\t{{.MemPerc}}"] + running_ids
                    stats_exit, stats_output = run_docker_command(stats_cmd)
                    if stats_exit == 0:
                        for stats_line in stats_output.split('\n'):
                            if stats_line:
                                stats_parts = stats_line.split('\t')
                                if len(stats_parts) == 3:
                                    self._stats_cache[stats_parts[0]] = {
                                        'cpu': stats_parts[1],
                                        'mem': stats_parts[2]
                                    }
                        self._stats_cache_time = current_time
            
            stats_data = self._stats_cache
        
        for line in lines:
            if line:
                parts = line.split('\t')
                if len(parts) == item_count:
                    row_data = list(parts)
                    
                    if self.mode == "CONTAINERS" and self._show_stats:
                        container_id = row_data[0][:12]
                        if container_id in stats_data:
                            row_data.append(stats_data[container_id]['cpu'])
                            row_data.append(stats_data[container_id]['mem'])
                        else:
                            row_data.extend(['--', '--'])
                    
                    marker = ' [X]' if self._multi_select_mode and row_data[0] in marked_ids else '    '
                    row_data.insert(0, marker)
                    table.add_row(*row_data, key=row_data[1])
        
        output_widget.update(f"OK: {len(lines)} items")

    def update_data_list(self) -> None:
        """Fast data update with optional stats."""
        self._update_single_table()
        
        # Force preview update after table is populated
        if self.mode == "CONTAINERS":
            table = self.query_one("#containers-table", DataTable)
            self.append_to_log(f"🔄 Table populated, row_count: {table.row_count}, cursor_row: {table.cursor_row}")
            if table.row_count > 0:
                if table.cursor_row is None:
                    table.move_cursor(row=0)
                    self.append_to_log(f"📍 Set cursor to row 0")
                self.call_after_refresh(self._force_initial_preview_update)

    def _force_initial_preview_update(self) -> None:
        """Force preview update after table is fully rendered."""
        try:
            # Get the current active table
            # if self.mode == "CONTAINERS":
            #     table = self.query_one("#containers-table", DataTable)
            # elif self.mode == "IMAGES":
            #     table = self.query_one("#images-table", DataTable)
            # else:
            #     table = self.query_one("#volumes-table", DataTable)
            table = self._get_current_table()
            if not table:
                return                
            if table.row_count > 0:
                cursor_row = table.cursor_row if table.cursor_row is not None else 0
                cell_key = table.coordinate_to_cell_key((cursor_row, 0))
                if cell_key and cell_key.row_key:
                    self.selected_row_data = list(table.get_row(cell_key.row_key))
                    self.append_to_log(f"✅ Initial preview: Got row data for row {cursor_row}")
                    self._update_preview_panel()
                else:
                    self.append_to_log(f"❌ Initial preview: No cell_key or row_key")
        except Exception as e:
            self.append_to_log(f"❌ Error in initial preview update: {e}")
    
    def action_launch_terminal_new(self) -> None:
        """Launch terminal in a new window/tab."""
        if self.mode != "CONTAINERS":
            self.notify("Terminal is only for containers.", severity="error")
            return
        
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return
        if table.cursor_row is None:
            return
        
        try:
            col_labels = [str(col.label) for col in table.columns.values()]
            id_idx = col_labels.index('ID')
            name_idx = col_labels.index('Names')
            status_idx = col_labels.index('Status')
        except:
            return
        
        row = table.get_row_at(table.cursor_row)
        cid, cname, status = row[id_idx], row[name_idx], row[status_idx]
        
        if 'up' not in status.lower():
            self.notify("Container not running.", severity="error")
            return
        
        # Platform-specific terminal launch (new window only)
        self.append_to_log(f"🔍 Platform detected: {PLATFORM}")
        launched = False
        if PLATFORM == "windows_wsl":
            # Try Windows Terminal with WSL first
            self.append_to_log(f"🪟 Trying Windows Terminal (wt.exe)...")
            cmd = ["wt.exe", "-w", "0", "--title", f"Terminal: {cname}", "wsl", "docker", "exec", "-it", cid, "/bin/bash"]
            try:
                subprocess.Popen(cmd, shell=False)
                self.notify(f"Terminal: {cname}", severity="information")
                self.append_to_log(f"✅ Windows Terminal launched successfully")
                launched = True
            except Exception as e:
                self.append_to_log(f"⚠️ Windows Terminal failed: {e}")
        elif PLATFORM == "linux":
            # Try common terminal emulators
            self.append_to_log(f"🐧 Trying Linux terminal emulators...")
            docker_cmd = f"docker exec -it {cid} /bin/bash"
            
            terminals = [
                ["x-terminal-emulator", "-e", docker_cmd],
                ["gnome-terminal", "--", "bash", "-c", docker_cmd],
                ["xterm", "-e", docker_cmd],
                ["konsole", "-e", docker_cmd],
            ]
            
            for term_cmd in terminals:
                try:
                    subprocess.Popen(term_cmd, shell=False)
                    self.notify(f"Terminal: {cname}", severity="information")
                    self.append_to_log(f"✅ Launched in {term_cmd[0]}")
                    launched = True
                    break
                except:
                    continue
        elif PLATFORM == "macos":
            # Try macOS Terminal.app first
            self.append_to_log(f"🍎 Trying macOS Terminal.app...")
            script = f'tell app "Terminal" to do script "docker exec -it {cid} /bin/bash"'
            cmd = ["osascript", "-e", script]
            try:
                subprocess.Popen(cmd, shell=False)
                self.notify(f"Terminal: {cname}", severity="information")
                self.append_to_log(f"✅ Terminal.app launched successfully")
                launched = True
            except Exception as e:
                self.append_to_log(f"⚠️ Terminal.app failed: {e}")
        
        if not launched:
            self.notify("No external terminal found. Use 't' for in-shell.", severity="warning")
            self.append_to_log(f"⚠️ No external terminal emulator found")
            self.append_to_log(f"💡 Try pressing 't' to run in-shell instead")

    def action_launch_terminal(self) -> None:
        """Launch terminal in the same shell (suspend TUI)."""
        if self.mode != "CONTAINERS":
            self.notify("Terminal is only for containers.", severity="error")
            return
        
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return
        if table.cursor_row is None:
            return
        
        try:
            col_labels = [str(col.label) for col in table.columns.values()]
            id_idx = col_labels.index('ID')
            name_idx = col_labels.index('Names')
            status_idx = col_labels.index('Status')
        except:
            return
        
        row = table.get_row_at(table.cursor_row)
        cid, cname, status = row[id_idx], row[name_idx], row[status_idx]
        
        if 'up' not in status.lower():
            self.notify("Container not running.", severity="error")
            return
        
        # Always use suspend method for in-shell terminal (t key)
        self.append_to_log(f"🔍 Platform detected: {PLATFORM}")
        docker_cmd = "docker"
        if PLATFORM == "windows_wsl":
            docker_cmd = "wsl docker"
        
        full_cmd = f"{docker_cmd} exec -it {cid} /bin/bash"
        
        try:
            with self.suspend():
                print(f"\n⏸️  Suspending TUI to run: {full_cmd}")
                print("💡 Press Ctrl+D or type 'exit' to return to NanoWhale\n")
                os.system(full_cmd)
                print("\n✅ Returning to NanoWhale...")
            
            self.notify("Terminal session ended", severity="information")
            self.append_to_log(f"✅ Terminal session completed: {cname}")
        except Exception as e:
            self.notify("Failed to launch terminal.", severity="error")
            self.append_to_log(f"❌ Error: {e}")

    def action_toggle_multi_select(self) -> None:
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return 
        current_data = None
        
        if table.cursor_row is not None:
            try:
                current_data = list(table.get_row_at(table.cursor_row))
            except:
                pass
        
        if current_data and len(current_data) > 1:
            row_data = current_data[1:]
            item_id = row_data[0]
            
            if self._multi_select_mode:
                is_marked = any(item[0] == item_id for item in self._selected_items)
                if is_marked:
                    self._selected_items = [item for item in self._selected_items if item[0] != item_id]
                    if not self._selected_items:
                        self._multi_select_mode = False
                        self.notify("Multi-select OFF", severity="information")
                    else:
                        self.notify(f"Unmarked ({len(self._selected_items)} selected)", timeout=1)
                else:
                    self._selected_items.append(row_data)
                    self.notify(f"Marked ({len(self._selected_items)} selected)", timeout=1)
                self.update_data_list()
            else:
                self._multi_select_mode = True
                self._selected_items.clear()
                self.notify("Multi-select ON. Press 'M' to mark.", severity="warning")
                self.update_data_list()

    def _execute_container_action(self, action: str) -> None:
        items = self._get_items_to_process()
        if not items:
            return

        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return    
        try:
            col_labels = [str(col.label) for col in table.columns.values()]
            id_idx = col_labels.index('ID')
            name_idx = col_labels.index('Names')
        except:
            id_idx, name_idx = 0, 2

        success = 0
        for item in items:
            cid, cname = item[id_idx], item[name_idx]
            if run_docker_command([action, cid])[0] == 0:
                success += 1
                self.append_to_log(f"✅ {action} {cname}")
            else:
                self.append_to_log(f"❌ Failed {action} {cname}")

        if success == len(items):
            self.notify(f"✅ {action}ed {success} container(s)", severity="information")
        elif success > 0:
            self.notify(f"⚠️ Partial: {success}/{len(items)}", severity="warning")
        else:
            self.notify(f"❌ Failed", severity="error")
        
        if self._multi_select_mode:
            self._selected_items.clear()
            self._multi_select_mode = False
        
        self.update_data_list()
        
    def action_restart_container(self) -> None:
        if self.mode != "CONTAINERS":
            return
        self._execute_container_action("restart")

    def action_stop_container(self) -> None:
        if self.mode != "CONTAINERS":
            return
        self._execute_container_action("stop")

    def action_start_container(self) -> None:
        if self.mode != "CONTAINERS":
            return
        self._execute_container_action("start")

    def action_watch_logs_new_terminal(self) -> None:
        """Watch logs in a new window/tab."""
        if self.mode != "CONTAINERS":
            self.notify("Logs only for containers.", severity="warning")
            return
        
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return            
        if table.cursor_row is None:
            return
        
        try:
            col_labels = [str(col.label) for col in table.columns.values()]
            id_idx = col_labels.index('ID')
            name_idx = col_labels.index('Names')
            status_idx = col_labels.index('Status')
        except:
            return
        
        row = table.get_row_at(table.cursor_row)
        cid, cname, status = row[id_idx], row[name_idx], row[status_idx]
        
        if 'up' not in status.lower():
            self.notify("Container not running.", severity="error")
            return
        
        # Platform-specific logs launch (new window only)
        self.append_to_log(f"🔍 Platform detected: {PLATFORM}")
        launched = False
        if PLATFORM == "windows_wsl":
            # Try Windows Terminal with WSL first
            self.append_to_log(f"🪟 Trying Windows Terminal (wt.exe)...")
            cmd = ["wt.exe", "-w", "0", "--title", f"Logs: {cname}", "wsl", "docker", "logs", "-f", "--tail", "50", cid]
            try:
                subprocess.Popen(cmd, shell=False)
                self.notify(f"Logs: {cname}", severity="information")
                self.append_to_log(f"✅ Windows Terminal launched successfully")
                launched = True
            except Exception as e:
                self.append_to_log(f"⚠️ Windows Terminal failed: {e}")
        elif PLATFORM == "linux":
            # Try common terminal emulators
            self.append_to_log(f"🐧 Trying Linux terminal emulators...")
            docker_cmd = f"docker logs -f --tail 50 {cid}"
            
            terminals = [
                ["x-terminal-emulator", "-e", "bash", "-c", docker_cmd],
                ["gnome-terminal", "--", "bash", "-c", docker_cmd],
                ["xterm", "-e", "bash", "-c", docker_cmd],
                ["konsole", "-e", "bash", "-c", docker_cmd],
            ]
            
            for term_cmd in terminals:
                try:
                    subprocess.Popen(term_cmd, shell=False)
                    self.notify(f"Logs: {cname}", severity="information")
                    self.append_to_log(f"✅ Launched in {term_cmd[0]}")
                    launched = True
                    break
                except:
                    continue
        elif PLATFORM == "macos":
            # Try macOS Terminal.app first
            self.append_to_log(f"🍎 Trying macOS Terminal.app...")
            script = f'tell app "Terminal" to do script "docker logs -f --tail 50 {cid}"'
            cmd = ["osascript", "-e", script]
            try:
                subprocess.Popen(cmd, shell=False)
                self.notify(f"Logs: {cname}", severity="information")
                self.append_to_log(f"✅ Terminal.app launched successfully")
                launched = True
            except Exception as e:
                self.append_to_log(f"⚠️ Terminal.app failed: {e}")
        
        if not launched:
            self.notify("No external terminal found. Use 'l' for in-shell.", severity="warning")
            self.append_to_log(f"⚠️ No external terminal emulator found")
            self.append_to_log(f"💡 Try pressing 'l' to view in-shell instead")

    def action_watch_logs(self) -> None:
        """Watch logs in the same shell (suspend TUI)."""
        if self.mode != "CONTAINERS":
            self.notify("Logs only for containers.", severity="warning")
            return
        
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return   
        if table.cursor_row is None:
            return
        
        try:
            col_labels = [str(col.label) for col in table.columns.values()]
            id_idx = col_labels.index('ID')
            name_idx = col_labels.index('Names')
            status_idx = col_labels.index('Status')
        except:
            return
        
        row = table.get_row_at(table.cursor_row)
        cid, cname, status = row[id_idx], row[name_idx], row[status_idx]
        
        if 'up' not in status.lower():
            self.notify("Container not running.", severity="error")
            return
        
        # Always use suspend method for in-shell logs (l key)
        self.append_to_log(f"🔍 Platform detected: {PLATFORM}")
        docker_cmd = "docker"
        if PLATFORM == "windows_wsl":
            docker_cmd = "wsl docker"
        
        full_cmd = f"{docker_cmd} logs -f --tail 50 {cid}"
        
        try:
            with self.suspend():
                print(f"\n⏸️  Suspending TUI to run: {full_cmd}")
                print("💡 Press Ctrl+C to stop logs and return to NanoWhale\n")
                os.system(full_cmd)
                print("\n✅ Returning to NanoWhale...")
            
            self.notify("Logs viewer ended", severity="information")
            self.append_to_log(f"✅ Logs viewing completed: {cname}")
        except Exception as e:
            self.notify("Failed to launch logs.", severity="error")
            self.append_to_log(f"❌ Error: {e}")

    def _get_items_to_process(self) -> list[list[str]] | None:
        # if self.mode == "CONTAINERS":
        #     table = self.query_one("#containers-table", DataTable)
        # elif self.mode == "IMAGES":
        #     table = self.query_one("#images-table", DataTable)
        # else:
        #     table = self.query_one("#volumes-table", DataTable)
        table = self._get_current_table()
        if not table:
            return
        if self._multi_select_mode:
            if not self._selected_items:
                self.notify("No items selected.", severity="warning")
                return None
            return self._selected_items
        else:
            if table.cursor_row is not None:
                try:
                    data = list(table.get_row_at(table.cursor_row))
                    return [data[1:]] if len(data) > 1 else None
                except:
                    pass
            self.notify("Select an item.", severity="warning")
            return None

    def action_delete_item(self) -> None:
        items = self._get_items_to_process()
        if not items:
            return

        table = self.query_one(DataTable)
        try:
            col_labels = [str(col.label) for col in table.columns.values()][1:]
            
            # Handle different column names for different modes
            if self.mode == "VOLUMES":
                id_idx = col_labels.index('Name')  # Volumes use 'Name' not 'ID'
                status_idx = None
            else:
                id_idx = col_labels.index('ID')
                status_idx = col_labels.index('Status') if self.mode == "CONTAINERS" else None
        except:
            self.notify("Column error.", severity="error")
            return

        success = 0
        for item in items:
            item_id = item[id_idx]
            
            if self.mode == "CONTAINERS":
                if status_idx is not None and 'up' in item[status_idx].lower():
                    self.notify(f"Stop {item_id[:12]} first.", severity="error")
                    continue
                cmd = ["rm", item_id]
            elif self.mode == "IMAGES":
                cmd = ["rmi", item_id]
            else:
                cmd = ["volume", "rm", item_id, "-f"]
            
            if run_docker_command(cmd)[0] == 0:
                success += 1
                self.append_to_log(f"✅ Deleted {item_id[:12]}")
            else:
                self.append_to_log(f"❌ Failed {item_id[:12]}")
        
        if success == len(items):
            self.notify(f"✅ Deleted {success} item(s)", severity="information")
        elif success > 0:
            self.notify(f"⚠️ Partial: {success}/{len(items)}", severity="warning")
        else:
            self.notify("❌ Delete failed", severity="error")

        if self._multi_select_mode:
            self._selected_items.clear()
        
        self.update_data_list()

    def append_to_log(self, text: str) -> None:
        panel = self.query_one("#log-panel", Static)
        current = panel.text if hasattr(panel, 'text') else ""
        if "Ready." in current or "Status/Output" in current:
            current = ""
        new_text = current + "\n" + text
        lines = new_text.splitlines()
        panel.update("\n".join(lines[-100:]))
        panel.scroll_end()

    def action_show_prune_menu(self) -> None:
        if self._prune_ready:
            if self._prune_timer:
                self._prune_timer.stop()
            self._prune_ready = False
            self._execute_prune()
        else:
            self._prune_ready = True
            self.notify("⚠️ Press 'P' again in 5s to prune.", severity="warning", timeout=5)
            self.append_to_log("WARN: Press 'P' again to prune unused Docker resources.")
            self._prune_timer = self.set_timer(5, self._reset_prune)

    def _reset_prune(self) -> None:
        self._prune_ready = False
        self._prune_timer = None
        self.notify("Prune cancelled.", severity="information")

    def _execute_prune(self) -> None:
        self.append_to_log("\n--- Starting Prune ---")
        exit_code, output = run_docker_command(["system", "prune", "-a", "-f"])
        if exit_code == 0:
            self.append_to_log(f"✅ Prune complete\n{output}")
            self.notify("✅ Prune complete", severity="information")
        else:
            self.append_to_log(f"❌ Prune failed\n{output}")
            self.notify("❌ Prune failed", severity="error")
        self.update_data_list()

    def action_quit(self) -> None:
        self.exit()


def main():
    app = DockerTUI()
    app.run()


if __name__ == "__main__":
    main()