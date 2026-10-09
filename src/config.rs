use std::time::Duration;

#[derive(Clone, Debug)]
pub struct Config {
    pub container_interval: Duration,
    pub misc_interval: Duration,
    pub stats_interval: Duration,
    pub stats_selective_interval: Duration,
    pub stats_all_container_max: usize,
    pub stats_parallel: usize,
    pub logs_tail: usize,
    pub logs_max_lines: usize,
    pub logs_timestamps: bool,
    pub log_flush_interval: Duration,
    pub max_history: usize,
    pub chart_width: usize,
    pub tick_rate: Duration,
    pub idle_tick_rate: Duration,
}

impl Default for Config {
    fn default() -> Self {
        Self::from_env()
    }
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            container_interval: secs_env("NW_CONTAINER_INTERVAL", 3),
            misc_interval: secs_env("NW_MISC_INTERVAL", 5),
            stats_interval: secs_env("NW_STATS_INTERVAL", 2),
            stats_selective_interval: secs_env("NW_STATS_SELECTIVE_INTERVAL", 1),
            stats_all_container_max: usize_env("NW_STATS_ALL_CONTAINER_MAX", 6),
            stats_parallel: usize_env("NW_STATS_PARALLEL", 4).clamp(1, 8),
            logs_tail: usize_env("NW_LOGS_TAIL", 200),
            logs_max_lines: usize_env("NW_LOGS_MAX_LINES", 2000),
            logs_timestamps: bool_env("NW_LOGS_TIMESTAMPS", false),
            log_flush_interval: millis_env("NW_LOG_FLUSH_MS", 120),
            max_history: usize_env("NW_MAX_HISTORY", 40),
            chart_width: usize_env("NW_CHART_WIDTH", 50),
            tick_rate: millis_env("NW_TICK_MS", 16),
            idle_tick_rate: millis_env("NW_IDLE_TICK_MS", 50),
        }
    }
}

fn usize_env(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn secs_env(key: &str, default: u64) -> Duration {
    Duration::from_secs(usize_env(key, default as usize) as u64)
}

fn millis_env(key: &str, default: u64) -> Duration {
    Duration::from_millis(usize_env(key, default as usize) as u64)
}

fn bool_env(key: &str, default: bool) -> bool {
    std::env::var(key)
        .ok()
        .map(|v| matches!(v.as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(default)
}
