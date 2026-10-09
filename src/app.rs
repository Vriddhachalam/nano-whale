use std::io::Write;
use std::process::{Command, Stdio};
use std::sync::{Arc, RwLock};

use bollard::Docker;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers, MouseButton, MouseEventKind};
use tokio::sync::mpsc::UnboundedReceiver;

use crate::chart::push_history;
use crate::config::Config;
use crate::docker::{
    container_remove, container_restart, container_start, container_stop, image_remove,
    load_inspect_tab, network_remove, spawn_logs, volume_remove, StatsTarget,
};
use crate::model::{AppState, ContentTab, DockerEvent, PanelFocus};

pub struct App {
    pub state: AppState,
    pub config: Config,
    pub docker: Docker,
    pub stats_target: Arc<RwLock<StatsTarget>>,
    pub log_task: Option<tokio::task::JoinHandle<()>>,
}

impl App {
    pub fn new(docker: Docker, config: Config, hostname: String) -> Self {
        Self {
            state: AppState {
                hostname,
                logs_auto_scroll: true,
                ..Default::default()
            },
            config,
            docker,
            stats_target: Arc::new(RwLock::new(StatsTarget::default())),
            log_task: None,
        }
    }

    pub fn bootstrap_streams(&mut self, tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>) {
        self.maybe_logs_stream(tx);
        self.maybe_load_detail(tx);
    }

    pub fn sync_stats_target(&self) {
        let name = self
            .state
            .selected_container()
            .map(|c| c.name.clone())
            .unwrap_or_default();
        let running: Vec<String> = self
            .state
            .containers
            .iter()
            .filter(|c| c.state == "running")
            .map(|c| c.name.clone())
            .collect();
        let mut t = self.stats_target.write().unwrap();
        t.container_count = self.state.containers.len();
        t.container_names = running;
        t.selected_name = name;
    }

    pub fn apply_event(
        &mut self,
        ev: DockerEvent,
        tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>,
    ) {
        match ev {
            DockerEvent::Containers(rows) => {
                self.state.containers = rows;
                self.state.inspect_cache.clear();
                if matches!(
                    self.state.tab,
                    ContentTab::Env | ContentTab::Config | ContentTab::Top
                ) {
                    self.state.detail_for = None;
                }
                self.state.clamp_selection();
                self.sync_stats_target();
            }
            DockerEvent::Images(rows) => {
                self.state.images = rows;
                self.state.clamp_selection();
            }
            DockerEvent::Volumes(rows) => {
                self.state.volumes = rows;
                self.state.clamp_selection();
            }
            DockerEvent::Networks(rows) => {
                self.state.networks = rows;
                self.state.clamp_selection();
            }
            DockerEvent::Stats(map) => {
                for (name, snap) in map {
                    push_history(
                        self.state.cpu_history.entry(name.clone()).or_default(),
                        snap.cpu_percent,
                        self.config.max_history,
                    );
                    push_history(
                        self.state.mem_history.entry(name.clone()).or_default(),
                        snap.mem_percent,
                        self.config.max_history,
                    );
                    self.state.stats.insert(name, snap);
                }
            }
            DockerEvent::Logs { container, chunk } => {
                let selected = self
                    .state
                    .selected_container()
                    .map(|c| c.name.clone());
                if selected.as_deref() == Some(container.as_str())
                    || self.state.logs_container.as_deref() == Some(container.as_str())
                {
                    self.state.logs = chunk;
                    if self.state.logs_auto_scroll {
                        self.state.content_scroll = 0;
                    }
                }
            }
            DockerEvent::InspectDetail { tab, container, text } => {
                let key = AppState::inspect_cache_key(tab, &container);
                self.state.inspect_cache.insert(key, text.clone());
                if self.state.detail_for.as_deref() == Some(container.as_str()) {
                    self.state.detail_loading = false;
                    match tab {
                        ContentTab::Env => self.state.env_text = text,
                        ContentTab::Config => self.state.config_text = text,
                        ContentTab::Top => self.state.top_text = text,
                        _ => {}
                    }
                }
            }
            DockerEvent::Notify { message, is_error } => {
                self.state.set_notify(message, is_error);
                return;
            }
        }
        self.state.mark_dirty();
        self.maybe_logs_stream(tx);
        self.maybe_load_detail(tx);
    }

    fn maybe_logs_stream(&mut self, tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>) {
        if self.state.tab != ContentTab::Logs {
            if let Some(task) = self.log_task.take() {
                task.abort();
            }
            self.state.logs_container = None;
            return;
        }
        let name = self
            .state
            .selected_container()
            .map(|c| c.name.clone())
            .unwrap_or_default();
        if name.is_empty() {
            return;
        }
        if self.state.logs_container.as_deref() == Some(name.as_str()) {
            return;
        }
        if let Some(task) = self.log_task.take() {
            task.abort();
        }
        self.state.logs.clear();
        let id = self
            .state
            .selected_container()
            .map(|c| c.id.clone())
            .unwrap_or_default();
        self.state.logs_container = Some(name.clone());
        self.log_task = Some(spawn_logs(
            self.docker.clone(),
            name,
            id,
            self.config.logs_tail,
            self.config.logs_max_lines,
            self.config.logs_timestamps,
            self.config.log_flush_interval,
            tx.clone(),
        ));
    }

    fn maybe_load_detail(&mut self, tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>) {
        let tab = self.state.tab;
        if !matches!(tab, ContentTab::Env | ContentTab::Config | ContentTab::Top) {
            return;
        }
        let name = self
            .state
            .selected_container()
            .map(|c| c.name.clone())
            .unwrap_or_default();
        if name.is_empty() {
            return;
        }
        let cache_key = AppState::inspect_cache_key(tab, &name);
        if let Some(cached) = self.state.inspect_cache.get(&cache_key) {
            self.state.detail_for = Some(name);
            self.state.detail_loading = false;
            match tab {
                ContentTab::Env => self.state.env_text = cached.clone(),
                ContentTab::Config => self.state.config_text = cached.clone(),
                ContentTab::Top => self.state.top_text = cached.clone(),
                _ => {}
            }
            return;
        }
        if self.state.detail_for.as_deref() == Some(name.as_str()) && self.state.detail_loading {
            return;
        }
        self.state.detail_for = Some(name.clone());
        self.state.detail_loading = true;
        load_inspect_tab(self.docker.clone(), tab, name, tx.clone());
    }

    pub fn handle_key(
        &mut self,
        key: KeyEvent,
        tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>,
    ) {
        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            self.state.quit = true;
            return;
        }
        if self.state.find_editing {
            self.handle_find_key(key);
            return;
        }
        match key.code {
            KeyCode::Char('q') => self.state.quit = true,
            KeyCode::Char('2') => self.state.focus = PanelFocus::Containers,
            KeyCode::Char('3') => self.state.focus = PanelFocus::Images,
            KeyCode::Char('4') => self.state.focus = PanelFocus::Volumes,
            KeyCode::Char('5') => self.state.focus = PanelFocus::Networks,
            KeyCode::Tab => {
                self.state.focus = match self.state.focus {
                    PanelFocus::Containers => PanelFocus::Images,
                    PanelFocus::Images => PanelFocus::Volumes,
                    PanelFocus::Volumes => PanelFocus::Networks,
                    PanelFocus::Networks => PanelFocus::Containers,
                };
            }
            KeyCode::Left => {
                self.state.tab = self.state.tab.prev();
                self.state.content_scroll = 0;
                self.state.detail_for = None;
                self.maybe_logs_stream(tx);
                self.maybe_load_detail(tx);
            }
            KeyCode::Right => {
                self.state.tab = self.state.tab.next();
                self.state.content_scroll = 0;
                self.state.detail_for = None;
                self.maybe_logs_stream(tx);
                self.maybe_load_detail(tx);
            }
            KeyCode::Up => self.nav_up(),
            KeyCode::Down => self.nav_down(),
            KeyCode::Esc if self.state.select_mode => {
                self.state.select_mode = false;
                self.state.selecting = false;
                self.state.drag_from = None;
                self.state.drag_to = None;
            }
            KeyCode::Esc => self.clear_find(),
            KeyCode::Home if self.state.tab == ContentTab::Logs => {
                self.state.logs_auto_scroll = false;
                self.state.content_scroll = 0;
            }
            KeyCode::End if self.state.tab == ContentTab::Logs => {
                self.state.logs_auto_scroll = true;
                self.state.content_scroll = 0;
            }
            KeyCode::Char('l') | KeyCode::Char('L') => self.request_terminal_logs(),
            KeyCode::Char('v') | KeyCode::Char('V') => {
                self.state.select_mode = !self.state.select_mode;
            }
            KeyCode::Char('/') => {
                if self.state.tab == ContentTab::Logs {
                    self.state.find_editing = true;
                }
            }
            KeyCode::Char('n') => self.find_next(true),
            KeyCode::Char('N') => self.find_next(false),
            KeyCode::Char('t') | KeyCode::Char('T') => self.request_terminal(),
            KeyCode::Char('s') => self.toggle_container(tx),
            KeyCode::Char('r') => self.restart_container(tx),
            KeyCode::Char('d') => self.delete_item(tx),
            KeyCode::Char('m') => self.toggle_mark(),
            KeyCode::Char('a') => {
                if self.state.tab == ContentTab::Logs {
                    if self.state.logs_auto_scroll {
                        self.state.logs_auto_scroll = false;
                        self.state.content_scroll = self.state.pane_scroll;
                    } else {
                        self.state.logs_auto_scroll = true;
                        self.state.content_scroll = 0;
                    }
                }
            }
            KeyCode::F(5) => {
                self.state.set_notify("Lists refresh automatically in background", false);
            }
            _ => {}
        }
        self.sync_stats_target();
        self.maybe_logs_stream(tx);
        self.maybe_load_detail(tx);
    }

    /// Positive delta scrolls toward newer lines; negative toward older.
    fn scroll_logs(&mut self, delta: i16) {
        if self.state.logs_auto_scroll {
            let lines = self.state.logs.lines().count();
            let visible = self.state.log_view_rows.max(1) as usize;
            self.state.content_scroll = lines.saturating_sub(visible) as u16;
            self.state.logs_auto_scroll = false;
        }
        if delta < 0 {
            self.state.content_scroll = self
                .state
                .content_scroll
                .saturating_sub((-delta) as u16);
        } else {
            self.state.content_scroll = self.state.content_scroll.saturating_add(delta as u16);
        }
        self.clamp_content_scroll();
    }

    pub fn handle_mouse(&mut self, kind: MouseEventKind, column: u16, row: u16) {
        match kind {
            MouseEventKind::ScrollUp => {
                if self.state.select_mode && self.on_right_pane(column, row) {
                    self.scroll_selection(-3);
                } else {
                    self.scroll_right_pane(column, row, -3);
                }
            }
            MouseEventKind::ScrollDown => {
                if self.state.select_mode && self.on_right_pane(column, row) {
                    self.scroll_selection(3);
                } else {
                    self.scroll_right_pane(column, row, 3);
                }
            }
            MouseEventKind::Down(MouseButton::Left) if self.state.select_mode => {
                if let Some(line) = self.pane_line_at(column, row) {
                    self.freeze_log_follow();
                    self.state.selecting = true;
                    self.state.drag_from = Some(line);
                    self.state.drag_to = Some(line);
                    self.state.mark_dirty();
                } else {
                    self.state.selecting = false;
                }
            }
            MouseEventKind::Drag(MouseButton::Left) if self.state.select_mode && self.state.selecting => {
                self.drag_select(column, row);
            }
            MouseEventKind::Up(MouseButton::Left) if self.state.select_mode && self.state.selecting => {
                self.state.selecting = false;
                self.copy_selection();
            }
            _ => {}
        }
    }

    fn on_right_pane(&self, column: u16, row: u16) -> bool {
        let Some((x, y, w, h)) = self.state.right_pane else {
            return false;
        };
        column >= x && column < x.saturating_add(w) && row >= y && row < y.saturating_add(h)
    }

    /// Scroll the right pane and grow the current selection with it.
    fn scroll_selection(&mut self, delta: i16) {
        if self.state.tab == ContentTab::Stats {
            return;
        }
        self.freeze_log_follow();
        if self.state.tab == ContentTab::Logs {
            self.scroll_logs(delta);
        } else if delta < 0 {
            self.state.content_scroll = self
                .state
                .content_scroll
                .saturating_sub((-delta) as u16);
        } else {
            self.state.content_scroll = self.state.content_scroll.saturating_add(delta as u16);
        }
        self.clamp_content_scroll();
        if self.state.drag_from.is_some() {
            self.shift_drag(delta);
        }
        self.state.mark_dirty();
    }

    fn shift_drag(&mut self, delta: i16) {
        let Some(to) = self.state.drag_to else {
            return;
        };
        let n = self.pane_source().lines().count();
        if n == 0 {
            return;
        }
        let next = if delta < 0 {
            to.saturating_sub((-delta) as usize)
        } else {
            to.saturating_add(delta as usize).min(n - 1)
        };
        self.state.drag_to = Some(next);
    }

    fn drag_select(&mut self, column: u16, row: u16) {
        let Some((x, y, w, h)) = self.state.pane_body else {
            return;
        };
        if h == 0 || column < x || column >= x.saturating_add(w) {
            return;
        }
        if row < y {
            self.scroll_selection(-1);
            return;
        }
        if row >= y.saturating_add(h) {
            self.scroll_selection(1);
            return;
        }
        if let Some(line) = self.pane_line_at(column, row) {
            self.state.drag_to = Some(line);
            self.state.mark_dirty();
        }
    }

    fn freeze_log_follow(&mut self) {
        if self.state.tab == ContentTab::Logs && self.state.logs_auto_scroll {
            self.state.logs_auto_scroll = false;
            self.state.content_scroll = self.state.pane_scroll;
        }
    }

    fn pane_line_at(&self, column: u16, row: u16) -> Option<usize> {
        let (x, y, w, h) = self.state.pane_body?;
        if column < x || column >= x.saturating_add(w) || row < y || row >= y.saturating_add(h) {
            return None;
        }
        let n = self.pane_source().lines().count();
        if n == 0 {
            return None;
        }
        Some((self.state.pane_scroll as usize + (row - y) as usize).min(n - 1))
    }

    fn clamp_content_scroll(&mut self) {
        let lines = self.pane_source().lines().count();
        let visible = self
            .state
            .pane_body
            .map(|(_, _, _, h)| h.max(1) as usize)
            .unwrap_or(self.state.log_view_rows.max(1) as usize);
        let max = lines.saturating_sub(visible) as u16;
        self.state.content_scroll = self.state.content_scroll.min(max);
    }

    fn copy_selection(&mut self) {
        let (Some(a), Some(b)) = (self.state.drag_from, self.state.drag_to) else {
            return;
        };
        let lines: Vec<&str> = self.pane_source().lines().collect();
        if lines.is_empty() {
            return;
        }
        let start = a.min(b).min(lines.len() - 1);
        let end = a.max(b).min(lines.len() - 1);
        let text = lines[start..=end].join("\n");
        if copy_to_clipboard(&text) {
            let n = end - start + 1;
            self.state.set_notify(format!("Copied {n} line{}", if n == 1 { "" } else { "s" }), false);
        } else {
            self.state.set_notify("Could not copy to clipboard", true);
        }
    }

    fn pane_source(&self) -> &str {
        match self.state.tab {
            ContentTab::Logs => &self.state.logs,
            ContentTab::Env => &self.state.env_text,
            ContentTab::Config => &self.state.config_text,
            ContentTab::Top => &self.state.top_text,
            ContentTab::Stats => "",
        }
    }

    pub fn scroll_right_pane(&mut self, column: u16, row: u16, delta: i16) {
        let Some((x, y, w, h)) = self.state.right_pane else {
            return;
        };
        let inside = column >= x && column < x.saturating_add(w) && row >= y && row < y.saturating_add(h);
        if !inside || self.state.tab != ContentTab::Logs {
            return;
        }
        self.scroll_logs(delta);
        self.state.mark_dirty();
    }

    fn clear_find(&mut self) {
        self.state.find_editing = false;
        self.state.find_query.clear();
        self.state.find_at = None;
    }

    fn handle_find_key(&mut self, key: KeyEvent) {
        match key.code {
            KeyCode::Esc => self.clear_find(),
            KeyCode::Enter => {
                self.state.find_editing = false;
                self.state.find_at = None;
                self.find_next(true);
            }
            KeyCode::Backspace => {
                self.state.find_query.pop();
            }
            KeyCode::Char(c) => self.state.find_query.push(c),
            _ => {}
        }
        self.state.mark_dirty();
    }

    fn find_next(&mut self, forward: bool) {
        if self.state.tab != ContentTab::Logs {
            return;
        }
        let query = self.state.find_query.trim().to_lowercase();
        if query.is_empty() {
            self.state.set_notify("Type / then a search", true);
            return;
        }
        let lines: Vec<String> = self.state.logs.lines().map(|s| s.to_string()).collect();
        if lines.is_empty() {
            self.state.set_notify("No logs to search", true);
            return;
        }
        let n = lines.len();
        let start = match self.state.find_at {
            Some(i) if forward => (i + 1) % n,
            Some(i) => (i + n - 1) % n,
            None => 0,
        };
        let mut i = start;
        for _ in 0..n {
            if lines[i].to_lowercase().contains(&query) {
                self.state.logs_auto_scroll = false;
                self.state.content_scroll = i as u16;
                self.state.find_at = Some(i);
                self.state.set_notify(format!("Match · line {}", i + 1), false);
                return;
            }
            i = if forward { (i + 1) % n } else { (i + n - 1) % n };
        }
        self.state.set_notify(format!("No match for {query}"), true);
    }

    fn request_terminal_logs(&mut self) {
        match self.state.selected_container() {
            Some(c) => self.state.logs_terminal = Some(c.name.clone()),
            None => self.state.set_notify("Select a container first", true),
        }
    }

    fn request_terminal(&mut self) {
        match self.state.selected_container() {
            Some(c) if c.state == "running" => {
                self.state.shell_container = Some(c.name.clone());
            }
            Some(c) => {
                self.state
                    .set_notify(format!("{} is not running", c.name), true);
            }
            None => self.state.set_notify("Select a container first", true),
        }
    }

    fn nav_up(&mut self) {
        if self.state.tab == ContentTab::Logs {
            self.state.logs_container = None;
        }
        match self.state.focus {
            PanelFocus::Containers if self.state.sel_container > 0 => self.state.sel_container -= 1,
            PanelFocus::Images if self.state.sel_image > 0 => self.state.sel_image -= 1,
            PanelFocus::Volumes if self.state.sel_volume > 0 => self.state.sel_volume -= 1,
            PanelFocus::Networks if self.state.sel_network > 0 => self.state.sel_network -= 1,
            _ => {}
        }
        self.state.content_scroll = 0;
        self.state.detail_for = None;
    }

    fn nav_down(&mut self) {
        if self.state.tab == ContentTab::Logs {
            self.state.logs_container = None;
        }
        match self.state.focus {
            PanelFocus::Containers if self.state.sel_container + 1 < self.state.containers.len() => {
                self.state.sel_container += 1;
            }
            PanelFocus::Images if self.state.sel_image + 1 < self.state.images.len() => {
                self.state.sel_image += 1;
            }
            PanelFocus::Volumes if self.state.sel_volume + 1 < self.state.volumes.len() => {
                self.state.sel_volume += 1;
            }
            PanelFocus::Networks if self.state.sel_network + 1 < self.state.networks.len() => {
                self.state.sel_network += 1;
            }
            _ => {}
        }
        self.state.content_scroll = 0;
        self.state.detail_for = None;
    }

    fn toggle_container(&mut self, tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>) {
        let docker = self.docker.clone();
        let tx = tx.clone();
        if let Some((name, state)) = self
            .state
            .selected_container()
            .map(|c| (c.name.clone(), c.state.clone()))
        {
            tokio::spawn(async move {
                let res = if state == "running" {
                    container_stop(&docker, &name).await
                } else {
                    container_start(&docker, &name).await
                };
                let is_error = res.is_err();
                let message = match res {
                    Ok(()) => format!("Updated {}", name),
                    Err(e) => format!("Action failed: {}", e),
                };
                let _ = tx.send(DockerEvent::Notify { message, is_error });
            });
        }
    }

    fn restart_container(&mut self, tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>) {
        let docker = self.docker.clone();
        let tx = tx.clone();
        if let Some(name) = self.state.selected_container().map(|c| c.name.clone()) {
            tokio::spawn(async move {
                let res = container_restart(&docker, &name).await;
                let is_error = res.is_err();
                let message = match res {
                    Ok(()) => format!("Restarted {}", name),
                    Err(e) => format!("Restart failed: {}", e),
                };
                let _ = tx.send(DockerEvent::Notify { message, is_error });
            });
        }
    }

    fn delete_item(&mut self, tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>) {
        let docker = self.docker.clone();
        let tx = tx.clone();
        match self.state.focus {
            PanelFocus::Containers => {
                if let Some(name) = self.state.selected_container().map(|c| c.name.clone()) {
                    tokio::spawn(async move {
                        let res = container_remove(&docker, &name).await;
                        let is_error = res.is_err();
                        let message = match res {
                            Ok(()) => format!("Deleted {}", name),
                            Err(e) => format!("Delete failed: {}", e),
                        };
                        let _ = tx.send(DockerEvent::Notify { message, is_error });
                    });
                }
            }
            PanelFocus::Images => {
                if let Some(id) = self.state.images.get(self.state.sel_image).map(|i| i.id.clone()) {
                    tokio::spawn(async move {
                        let res = image_remove(&docker, &id).await;
                        let is_error = res.is_err();
                        let message = match res {
                            Ok(()) => "Image deleted".into(),
                            Err(e) => format!("Delete failed: {}", e),
                        };
                        let _ = tx.send(DockerEvent::Notify { message, is_error });
                    });
                }
            }
            PanelFocus::Volumes => {
                if let Some(name) = self.state.volumes.get(self.state.sel_volume).map(|v| v.name.clone()) {
                    tokio::spawn(async move {
                        let res = volume_remove(&docker, &name).await;
                        let is_error = res.is_err();
                        let message = match res {
                            Ok(()) => format!("Deleted volume {}", name),
                            Err(e) => format!("Delete failed: {}", e),
                        };
                        let _ = tx.send(DockerEvent::Notify { message, is_error });
                    });
                }
            }
            PanelFocus::Networks => {
                if let Some(name) = self.state.networks.get(self.state.sel_network).map(|n| n.name.clone()) {
                    tokio::spawn(async move {
                        let res = network_remove(&docker, &name).await;
                        let is_error = res.is_err();
                        let message = match res {
                            Ok(()) => format!("Deleted network {}", name),
                            Err(e) => format!("Delete failed: {}", e),
                        };
                        let _ = tx.send(DockerEvent::Notify { message, is_error });
                    });
                }
            }
        }
    }

    fn toggle_mark(&mut self) {
        match self.state.focus {
            PanelFocus::Containers => {
                if let Some(name) = self.state.selected_container().map(|c| c.name.clone()) {
                    if self.state.marked_containers.contains(&name) {
                        self.state.marked_containers.remove(&name);
                    } else {
                        self.state.marked_containers.insert(name);
                    }
                }
            }
            PanelFocus::Images => {
                if let Some(id) = self.state.images.get(self.state.sel_image).map(|i| i.id.clone()) {
                    if self.state.marked_images.contains(&id) {
                        self.state.marked_images.remove(&id);
                    } else {
                        self.state.marked_images.insert(id);
                    }
                }
            }
            PanelFocus::Volumes => {
                if let Some(name) = self.state.volumes.get(self.state.sel_volume).map(|v| v.name.clone()) {
                    if self.state.marked_volumes.contains(&name) {
                        self.state.marked_volumes.remove(&name);
                    } else {
                        self.state.marked_volumes.insert(name);
                    }
                }
            }
            PanelFocus::Networks => {}
        }
    }

    pub fn drain_events(
        &mut self,
        rx: &mut UnboundedReceiver<DockerEvent>,
        tx: &tokio::sync::mpsc::UnboundedSender<DockerEvent>,
    ) {
        while let Ok(ev) = rx.try_recv() {
            self.apply_event(ev, tx);
        }
    }
}

fn copy_to_clipboard(text: &str) -> bool {
    if let Ok(mut clipboard) = arboard::Clipboard::new() {
        clipboard.set_text(text).is_ok()
    } else {
        false
    }
}
