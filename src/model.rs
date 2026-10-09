use std::collections::{HashMap, HashSet};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PanelFocus {
    Containers,
    Images,
    Volumes,
    Networks,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ContentTab {
    Logs,
    Stats,
    Env,
    Config,
    Top,
}

impl ContentTab {
    pub fn next(self) -> Self {
        match self {
            Self::Logs => Self::Stats,
            Self::Stats => Self::Env,
            Self::Env => Self::Config,
            Self::Config => Self::Top,
            Self::Top => Self::Logs,
        }
    }

    pub fn prev(self) -> Self {
        match self {
            Self::Logs => Self::Top,
            Self::Stats => Self::Logs,
            Self::Env => Self::Stats,
            Self::Config => Self::Env,
            Self::Top => Self::Config,
        }
    }

    pub fn title(self) -> &'static str {
        match self {
            Self::Logs => "Logs",
            Self::Stats => "Stats",
            Self::Env => "Env",
            Self::Config => "Config",
            Self::Top => "Top",
        }
    }

    pub fn glyph(self) -> &'static str {
        match self {
            Self::Logs => "▤",
            Self::Stats => "◢",
            Self::Env => "◇",
            Self::Config => "⚙",
            Self::Top => "☰",
        }
    }
}

impl PanelFocus {
    pub fn hotkey(self) -> char {
        match self {
            Self::Containers => '2',
            Self::Images => '3',
            Self::Volumes => '4',
            Self::Networks => '5',
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Containers => "Containers",
            Self::Images => "Images",
            Self::Volumes => "Volumes",
            Self::Networks => "Networks",
        }
    }
}

#[derive(Clone, Debug)]
pub struct ContainerRow {
    pub id: String,
    pub name: String,
    pub state: String,
    pub image: String,
    pub ports: String,
}

#[derive(Clone, Debug)]
pub struct ImageRow {
    pub id: String,
    pub repo: String,
    pub tag: String,
    pub size: String,
}

#[derive(Clone, Debug)]
pub struct VolumeRow {
    pub name: String,
    pub driver: String,
}

#[derive(Clone, Debug)]
pub struct NetworkRow {
    pub name: String,
    pub driver: String,
}

#[derive(Clone, Debug, Default)]
pub struct StatsSnapshot {
    pub cpu_percent: f64,
    pub mem_percent: f64,
    pub mem_usage: String,
    pub net_io: String,
    pub block_io: String,
    pub pids: String,
}

#[derive(Debug)]
pub enum DockerEvent {
    Containers(Vec<ContainerRow>),
    Images(Vec<ImageRow>),
    Volumes(Vec<VolumeRow>),
    Networks(Vec<NetworkRow>),
    Stats(HashMap<String, StatsSnapshot>),
    Logs { container: String, chunk: String },
    InspectDetail { tab: ContentTab, container: String, text: String },
    Notify { message: String, is_error: bool },
}

#[derive(Debug)]
pub struct AppState {
    pub hostname: String,
    pub containers: Vec<ContainerRow>,
    pub images: Vec<ImageRow>,
    pub volumes: Vec<VolumeRow>,
    pub networks: Vec<NetworkRow>,

    pub sel_container: usize,
    pub sel_image: usize,
    pub sel_volume: usize,
    pub sel_network: usize,
    pub focus: PanelFocus,
    pub tab: ContentTab,

    pub marked_containers: HashSet<String>,
    pub marked_images: HashSet<String>,
    pub marked_volumes: HashSet<String>,

    pub stats: HashMap<String, StatsSnapshot>,
    pub cpu_history: HashMap<String, Vec<f64>>,
    pub mem_history: HashMap<String, Vec<f64>>,

    pub logs: String,
    pub logs_container: Option<String>,
    pub logs_auto_scroll: bool,
    pub content_scroll: u16,

    pub env_text: String,
    pub config_text: String,
    pub top_text: String,
    pub detail_loading: bool,
    pub detail_for: Option<String>,

    pub notify: Option<NotifyMessage>,
    pub inspect_cache: HashMap<String, String>,
    pub shell_container: Option<String>,
    pub logs_terminal: Option<String>,
    pub right_pane: Option<(u16, u16, u16, u16)>,
    pub pane_body: Option<(u16, u16, u16, u16)>,
    pub pane_scroll: u16,
    pub drag_from: Option<usize>,
    pub drag_to: Option<usize>,
    pub selecting: bool,
    pub log_view_rows: u16,
    pub find_query: String,
    pub find_editing: bool,
    pub find_at: Option<usize>,
    pub select_mode: bool,
    pub dirty: bool,
    pub quit: bool,
}

#[derive(Clone, Debug)]
pub struct NotifyMessage {
    pub text: String,
    pub until: std::time::Instant,
    pub is_error: bool,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            hostname: String::new(),
            containers: Vec::new(),
            images: Vec::new(),
            volumes: Vec::new(),
            networks: Vec::new(),
            sel_container: 0,
            sel_image: 0,
            sel_volume: 0,
            sel_network: 0,
            focus: PanelFocus::Containers,
            tab: ContentTab::Logs,
            marked_containers: HashSet::new(),
            marked_images: HashSet::new(),
            marked_volumes: HashSet::new(),
            stats: HashMap::new(),
            cpu_history: HashMap::new(),
            mem_history: HashMap::new(),
            logs: String::new(),
            logs_container: None,
            logs_auto_scroll: true,
            content_scroll: 0,
            env_text: String::new(),
            config_text: String::new(),
            top_text: String::new(),
            detail_loading: false,
            detail_for: None,
            notify: None,
            inspect_cache: HashMap::new(),
            shell_container: None,
            logs_terminal: None,
            right_pane: None,
            pane_body: None,
            pane_scroll: 0,
            drag_from: None,
            drag_to: None,
            selecting: false,
            log_view_rows: 1,
            find_query: String::new(),
            find_editing: false,
            find_at: None,
            select_mode: false,
            dirty: true,
            quit: false,
        }
    }
}

impl AppState {
    pub fn selected_container(&self) -> Option<&ContainerRow> {
        self.containers.get(self.sel_container)
    }

    pub fn clamp_selection(&mut self) {
        if !self.containers.is_empty() {
            self.sel_container = self.sel_container.min(self.containers.len() - 1);
        } else {
            self.sel_container = 0;
        }
        if !self.images.is_empty() {
            self.sel_image = self.sel_image.min(self.images.len() - 1);
        } else {
            self.sel_image = 0;
        }
        if !self.volumes.is_empty() {
            self.sel_volume = self.sel_volume.min(self.volumes.len() - 1);
        } else {
            self.sel_volume = 0;
        }
        if !self.networks.is_empty() {
            self.sel_network = self.sel_network.min(self.networks.len() - 1);
        } else {
            self.sel_network = 0;
        }
    }

    pub fn set_notify(&mut self, message: impl Into<String>, is_error: bool) {
        self.notify = Some(NotifyMessage {
            text: message.into(),
            until: std::time::Instant::now() + std::time::Duration::from_secs(2),
            is_error,
        });
        self.dirty = true;
    }

    pub fn mark_dirty(&mut self) {
        self.dirty = true;
    }

    pub fn inspect_cache_key(tab: ContentTab, container: &str) -> String {
        format!("{}:{}", tab.title(), container)
    }
}
