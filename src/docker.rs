use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

use anyhow::Context;
use bollard::container::{ListContainersOptions, LogsOptions, StatsOptions, TopOptions};
use bollard::image::ListImagesOptions;
use bollard::network::ListNetworksOptions;
use bollard::volume::ListVolumesOptions;
use bollard::Docker;
use futures::stream::{self, StreamExt};
use tokio::sync::mpsc::UnboundedSender;
use tokio::time::{interval, MissedTickBehavior};

use crate::config::Config;
use crate::model::{
    ContainerRow, ContentTab, DockerEvent, ImageRow, NetworkRow, StatsSnapshot, VolumeRow,
};
use crate::stats_parse::snapshot_from_docker;
use crate::textutil::clip_line;

pub type EventTx = UnboundedSender<DockerEvent>;

#[derive(Clone, Default)]
pub struct StatsTarget {
    pub container_count: usize,
    pub container_names: Vec<String>,
    pub selected_name: String,
}

pub fn connect() -> anyhow::Result<Docker> {
    Docker::connect_with_local_defaults().context("connect to Docker (is the daemon running?)")
}

pub fn spawn_workers(
    docker: Docker,
    config: Config,
    tx: EventTx,
    stats_target: Arc<RwLock<StatsTarget>>,
) {
    tokio::spawn(poll_containers(docker.clone(), config.container_interval, tx.clone()));
    tokio::spawn(poll_misc(docker.clone(), config.misc_interval, tx.clone()));
    tokio::spawn(poll_stats(docker.clone(), config, tx, stats_target));
}

async fn poll_containers(docker: Docker, every: Duration, tx: EventTx) {
    let mut last_fp = String::new();
    let mut tick = interval(every);
    tick.set_missed_tick_behavior(MissedTickBehavior::Skip);
    loop {
        match fetch_containers(&docker).await {
            Ok(rows) => {
                let fp = container_fingerprint(&rows);
                if fp != last_fp {
                    last_fp = fp;
                    let _ = tx.send(DockerEvent::Containers(rows));
                }
            }
            Err(e) => {
                let _ = tx.send(DockerEvent::Notify {
                    message: format!("docker ps failed: {}", e),
                    is_error: true,
                });
            }
        }
        tick.tick().await;
    }
}

async fn fetch_containers(docker: &Docker) -> anyhow::Result<Vec<ContainerRow>> {
    let opts = Some(ListContainersOptions::<String> {
        all: true,
        ..Default::default()
    });
    match docker.list_containers(opts).await {
        Ok(list) => Ok(
            list.into_iter()
                .map(|c| {
                    let name = c
                        .names
                        .and_then(|n| n.first().cloned())
                        .map(|n| n.trim_start_matches('/').to_string())
                        .unwrap_or_else(|| "unknown".into());
                    let state = c.state.unwrap_or_else(|| "unknown".into());
                    let id = c.id.unwrap_or_default();
                    let image = c.image.unwrap_or_else(|| "N/A".into());
                    let ports = c
                        .ports
                        .unwrap_or_default()
                        .into_iter()
                        .map(|p| {
                            let pub_p = p
                                .public_port
                                .map(|pp| format!(":{}", pp))
                                .unwrap_or_default();
                            format!("{}{}", p.private_port, pub_p)
                        })
                        .collect::<Vec<_>>()
                        .join(",");
                    ContainerRow {
                        id,
                        name,
                        state,
                        image,
                        ports,
                    }
                })
                .collect(),
        ),
        Err(e) => Err(e.into()),
    }
}

fn container_fingerprint(rows: &[ContainerRow]) -> String {
    rows.iter()
        .map(|r| format!("{}|{}|{}", r.name, r.state, r.ports))
        .collect::<Vec<_>>()
        .join(";")
}

async fn poll_misc(docker: Docker, every: Duration, tx: EventTx) {
    let mut tick = interval(every);
    tick.set_missed_tick_behavior(MissedTickBehavior::Skip);
    loop {
        if let Ok(imgs) = docker
            .list_images(Some(ListImagesOptions::<String> {
                all: true,
                ..Default::default()
            }))
            .await
        {
            let rows = imgs
                .into_iter()
                .map(|i| {
                    let repo = i
                        .repo_tags
                        .first()
                        .cloned()
                        .unwrap_or_else(|| "<none>:<none>".into());
                    let (repo, tag) = match repo.split_once(':') {
                        Some((r, t)) => (r.to_string(), t.to_string()),
                        None => (repo, "latest".into()),
                    };
                    ImageRow {
                        id: i.id.chars().take(12).collect(),
                        repo,
                        tag,
                        size: format_size(i.size),
                    }
                })
                .collect();
            let _ = tx.send(DockerEvent::Images(rows));
        }

        if let Ok(vols) = docker
            .list_volumes(Some(ListVolumesOptions::<String> {
                ..Default::default()
            }))
            .await
        {
            let rows = vols
                .volumes
                .unwrap_or_default()
                .into_iter()
                .map(|v| VolumeRow {
                    name: v.name,
                    driver: if v.driver.is_empty() { "local".into() } else { v.driver },
                })
                .collect();
            let _ = tx.send(DockerEvent::Volumes(rows));
        }

        if let Ok(nets) = docker
            .list_networks(Some(ListNetworksOptions::<String> {
                ..Default::default()
            }))
            .await
        {
            let rows = nets
                .into_iter()
                .map(|n| NetworkRow {
                    name: n.name.unwrap_or_default(),
                    driver: n.driver.unwrap_or_else(|| "bridge".into()),
                })
                .collect();
            let _ = tx.send(DockerEvent::Networks(rows));
        }

        tick.tick().await;
    }
}

async fn poll_stats(
    docker: Docker,
    config: Config,
    tx: EventTx,
    target: Arc<RwLock<StatsTarget>>,
) {
    let mut tick = interval(config.stats_selective_interval);
    tick.set_missed_tick_behavior(MissedTickBehavior::Skip);
    loop {
        let (count, selected, names) = {
            let t = target.read().unwrap();
            (t.container_count, t.selected_name.clone(), t.container_names.clone())
        };
        let selective = count > config.stats_all_container_max;
        let wait = if selective {
            config.stats_selective_interval
        } else {
            config.stats_interval
        };
        if tick.period() != wait {
            tick = interval(wait);
            tick.set_missed_tick_behavior(MissedTickBehavior::Skip);
        }

        let result = if selective {
            if selected.is_empty() {
                tick.tick().await;
                continue;
            }
            stats_one(&docker, &selected).await
        } else {
            stats_many(&docker, &names, config.stats_parallel).await
        };
        if let Ok(map) = result {
            if !map.is_empty() {
                let _ = tx.send(DockerEvent::Stats(map));
            }
        }
        tick.tick().await;
    }
}

async fn stats_many(
    docker: &Docker,
    names: &[String],
    parallel: usize,
) -> anyhow::Result<HashMap<String, StatsSnapshot>> {
    let parallel = parallel.clamp(1, 8);
    let mut map = HashMap::new();
    let mut merged = stream::iter(names.iter().cloned())
        .map(|name| {
            let docker = docker.clone();
            async move { stats_one(&docker, &name).await }
        })
        .buffer_unordered(parallel);
    while let Some(res) = merged.next().await {
        if let Ok(one) = res {
            map.extend(one);
        }
    }
    Ok(map)
}

async fn stats_one(docker: &Docker, name: &str) -> anyhow::Result<HashMap<String, StatsSnapshot>> {
    let opts = Some(StatsOptions {
        stream: false,
        one_shot: true,
    });
    let mut stream = docker.stats(name, opts);
    let mut map = HashMap::new();
    if let Some(item) = stream.next().await {
        let s = item?;
        let key = s.name.trim_start_matches('/');
        let key = if key.is_empty() { name } else { key };
        map.insert(key.to_string(), snapshot_from_docker(&s));
    }
    Ok(map)
}

fn format_size(bytes: i64) -> String {
    const UNITS: &[&str] = &["B", "kB", "MB", "GB"];
    let mut n = bytes as f64;
    let mut i = 0;
    while n >= 1024.0 && i < UNITS.len() - 1 {
        n /= 1024.0;
        i += 1;
    }
    format!("{:.1}{}", n, UNITS[i])
}

#[allow(clippy::too_many_arguments)]
pub fn spawn_logs(
    docker: Docker,
    container: String,
    container_id: String,
    tail: usize,
    max_lines: usize,
    timestamps: bool,
    flush_every: Duration,
    tx: EventTx,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let tail_s = tail.to_string();
        let mut targets = vec![container.clone()];
        if !container_id.is_empty() && container_id != container {
            targets.push(container_id);
        }

        let mut buf = String::new();
        let mut attached = false;

        for target in targets {
            if pull_logs_snapshot(
                &docker,
                &target,
                &tail_s,
                timestamps,
                max_lines,
                &container,
                &tx,
                &mut buf,
            )
            .await
            {
                attached = true;
                follow_logs_live(
                    &docker,
                    &target,
                    timestamps,
                    max_lines,
                    flush_every,
                    &container,
                    &tx,
                    &mut buf,
                )
                .await;
                break;
            }
        }

        if !attached {
            let msg = format!(
                "Could not read logs for '{}'.\n\nShell equivalent:\n  docker logs --tail {} -f {}\n",
                container,
                tail,
                container
            );
            let _ = tx.send(DockerEvent::Logs {
                container: container.clone(),
                chunk: msg,
            });
        }
    })
}

fn logs_options(tail: &str, follow: bool, timestamps: bool) -> Option<LogsOptions<String>> {
    Some(LogsOptions {
        stdout: true,
        stderr: true,
        follow,
        timestamps,
        tail: tail.to_string(),
        ..Default::default()
    })
}

#[allow(clippy::too_many_arguments)]
async fn pull_logs_snapshot(
    docker: &Docker,
    target: &str,
    tail: &str,
    timestamps: bool,
    max_lines: usize,
    container_key: &str,
    tx: &EventTx,
    buf: &mut String,
) -> bool {
    for attempt in 0..3 {
        let mut stream = docker.logs(target, logs_options(tail, false, timestamps));
        let mut got = false;
        while let Some(chunk) = stream.next().await {
            match chunk {
                Ok(log) => {
                    got = true;
                    append_log_line(buf, log);
                }
                Err(e) => {
                    if buf.is_empty() {
                        buf.push_str(&format!("docker logs error: {}\n", e));
                    }
                    break;
                }
            }
        }
        if got || !buf.is_empty() {
            trim_log_buffer(buf, max_lines);
            let _ = tx.send(DockerEvent::Logs {
                container: container_key.to_string(),
                chunk: buf.clone(),
            });
            return true;
        }
        if attempt < 2 {
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
    }
    false
}

#[allow(clippy::too_many_arguments)]
async fn follow_logs_live(
    docker: &Docker,
    target: &str,
    timestamps: bool,
    max_lines: usize,
    flush_every: Duration,
    container_key: &str,
    tx: &EventTx,
    buf: &mut String,
) {
    let mut stream = docker.logs(target, logs_options("0", true, timestamps));
    let mut last_flush = Instant::now();
    while let Some(chunk) = stream.next().await {
        match chunk {
            Ok(log) => {
                append_log_line(buf, log);
                trim_log_buffer(buf, max_lines);
                if last_flush.elapsed() >= flush_every {
                    last_flush = Instant::now();
                    let _ = tx.send(DockerEvent::Logs {
                        container: container_key.to_string(),
                        chunk: buf.clone(),
                    });
                }
            }
            Err(e) => {
                buf.push_str(&format!("\n[log stream ended: {}]\n", e));
                let _ = tx.send(DockerEvent::Logs {
                    container: container_key.to_string(),
                    chunk: buf.clone(),
                });
                break;
            }
        }
    }
    if last_flush.elapsed() < flush_every {
        let _ = tx.send(DockerEvent::Logs {
            container: container_key.to_string(),
            chunk: buf.clone(),
        });
    }
}

fn append_log_line(buf: &mut String, log: bollard::container::LogOutput) {
    use bollard::container::LogOutput;
    let piece = match log {
        LogOutput::StdOut { message }
        | LogOutput::StdErr { message }
        | LogOutput::StdIn { message }
        | LogOutput::Console { message } => String::from_utf8_lossy(&message).into_owned(),
    };
    let normalized = piece.replace("\r\n", "\n").replace('\r', "\n");
    buf.push_str(&normalized);
}

fn trim_log_buffer(buf: &mut String, max_lines: usize) {
    let line_count = buf.lines().count();
    if line_count <= max_lines {
        return;
    }
    let skip = line_count - max_lines;
    let lines: Vec<&str> = buf.lines().collect();
    *buf = lines[skip..].join("\n");
    if !buf.ends_with('\n') {
        buf.push('\n');
    }
}

pub fn load_inspect_tab(docker: Docker, tab: ContentTab, container: String, tx: EventTx) {
    tokio::spawn(async move {
        let text = match tab {
            ContentTab::Env => fetch_env(&docker, &container).await,
            ContentTab::Config => fetch_config(&docker, &container).await,
            ContentTab::Top => fetch_top(&docker, &container).await,
            _ => Ok(String::new()),
        };
        let text = text.unwrap_or_else(|e| format!("Error: {}", e));
        let _ = tx.send(DockerEvent::InspectDetail {
            tab,
            container,
            text,
        });
    });
}

async fn fetch_env(docker: &Docker, name: &str) -> anyhow::Result<String> {
    let inspect = docker.inspect_container(name, None).await?;
    let env = inspect.config.and_then(|c| c.env).unwrap_or_default();
    Ok(env.join("\n"))
}

async fn fetch_config(docker: &Docker, name: &str) -> anyhow::Result<String> {
    let inspect = docker.inspect_container(name, None).await?;
    let id = inspect.id.clone().unwrap_or_default();
    let image = inspect
        .config
        .as_ref()
        .and_then(|c| c.image.clone())
        .unwrap_or_else(|| "N/A".into());
    let state = inspect
        .state
        .as_ref()
        .and_then(|s| s.status.as_ref())
        .map(|s| format!("{:?}", s))
        .unwrap_or_else(|| "unknown".into());
    let mut out = format!(
        "Configuration: {}\n{}\n\nID:      {}\nImage:   {}\nState:   {}\n",
        name,
        "-".repeat(55),
        id.chars().take(12).collect::<String>(),
        image,
        state
    );
    out.push_str("\n(Full inspect available via docker inspect)\n");
    let pretty = serde_json::to_string_pretty(&inspect)?;
    for (i, line) in pretty.lines().enumerate() {
        if i >= 120 {
            out.push_str("\n... truncated ...\n");
            break;
        }
        out.push_str(line);
        out.push('\n');
    }
    Ok(out)
}

async fn fetch_top(docker: &Docker, name: &str) -> anyhow::Result<String> {
    let top = docker
        .top_processes(name, Some(TopOptions { ps_args: "-aux" }))
        .await?;
    let mut out = String::new();
    const MAX_COL: usize = 120;
    if let Some(titles) = top.titles {
        out.push_str(&clip_line(&titles.join(" "), MAX_COL));
        out.push('\n');
    }
    for row in top.processes.unwrap_or_default() {
        out.push_str(&clip_line(&row.join(" "), MAX_COL));
        out.push('\n');
    }
    Ok(out)
}

pub async fn container_start(docker: &Docker, name: &str) -> anyhow::Result<()> {
    docker
        .start_container(name, None::<bollard::container::StartContainerOptions<String>>)
        .await?;
    Ok(())
}

pub async fn container_stop(docker: &Docker, name: &str) -> anyhow::Result<()> {
    docker.stop_container(name, None).await?;
    Ok(())
}

pub async fn container_restart(docker: &Docker, name: &str) -> anyhow::Result<()> {
    docker.restart_container(name, None).await?;
    Ok(())
}

pub async fn container_remove(docker: &Docker, name: &str) -> anyhow::Result<()> {
    docker.remove_container(name, None).await?;
    Ok(())
}

pub async fn image_remove(docker: &Docker, id: &str) -> anyhow::Result<()> {
    docker.remove_image(id, None, None).await?;
    Ok(())
}

pub async fn volume_remove(docker: &Docker, name: &str) -> anyhow::Result<()> {
    docker.remove_volume(name, None).await?;
    Ok(())
}

pub async fn network_remove(docker: &Docker, name: &str) -> anyhow::Result<()> {
    if matches!(name, "bridge" | "host" | "none") {
        anyhow::bail!("cannot delete system network");
    }
    docker.remove_network(name).await?;
    Ok(())
}
