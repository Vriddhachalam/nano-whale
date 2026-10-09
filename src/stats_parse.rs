use bollard::container::Stats;

use crate::model::StatsSnapshot;

pub fn snapshot_from_docker(s: &Stats) -> StatsSnapshot {
    let cpu_percent = cpu_percent(s);
    let usage = s.memory_stats.usage.unwrap_or(0);
    let limit = s.memory_stats.limit.unwrap_or(1).max(1);
    let mem_percent = (usage as f64 / limit as f64 * 100.0).min(100.0);
    let pids = s.pids_stats.current.unwrap_or(0);

    let (net_rx, net_tx) = net_totals(s);
    let net_io = format!("{} / {}", net_rx, net_tx);

    StatsSnapshot {
        cpu_percent,
        mem_percent,
        mem_usage: human_bytes(usage as f64) + " / " + &human_bytes(limit as f64),
        net_io,
        block_io: "N/A".into(),
        pids: pids.to_string(),
    }
}

fn cpu_percent(s: &Stats) -> f64 {
    let cpu = &s.cpu_stats;
    let pre = &s.precpu_stats;
    let usage = cpu.cpu_usage.total_usage;
    let pre_usage = pre.cpu_usage.total_usage;
    let sys = cpu.system_cpu_usage.unwrap_or(0);
    let pre_sys = pre.system_cpu_usage.unwrap_or(0);
    let cpu_delta = usage.saturating_sub(pre_usage);
    let sys_delta = sys.saturating_sub(pre_sys);
    if sys_delta == 0 {
        return 0.0;
    }
    let cpus = cpu.online_cpus.unwrap_or(1) as f64;
    let pct = (cpu_delta as f64 / sys_delta as f64) * cpus * 100.0;
    pct.clamp(0.0, 100.0 * cpus)
}

fn net_totals(s: &Stats) -> (String, String) {
    let mut rx = 0u64;
    let mut tx = 0u64;
    if let Some(nets) = &s.networks {
        for n in nets.values() {
            rx += n.rx_bytes;
            tx += n.tx_bytes;
        }
    }
    (human_bytes(rx as f64), human_bytes(tx as f64))
}

fn human_bytes(n: f64) -> String {
    const UNITS: &[&str] = &["B", "kB", "MB", "GB", "TB"];
    let mut v = n;
    let mut i = 0;
    while v >= 1024.0 && i < UNITS.len() - 1 {
        v /= 1024.0;
        i += 1;
    }
    format!("{:.1}{}", v, UNITS[i])
}
