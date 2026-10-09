use ratatui::symbols::bar;

/// Prepare percentage history (0–100) for rendering at exactly `width` columns.
/// Older samples on the left, newest on the right; pads left with zeros when warming up.
/// When downsampling, each bucket uses the **max** so spikes are not lost.
pub fn percent_series(values: &[f64], width: usize) -> Vec<u64> {
    let width = width.max(1);
    let resampled = resample(values, width);
    resampled
        .into_iter()
        .map(|v| v.clamp(0.0, 100.0).round() as u64)
        .collect()
}

/// Human-readable sparkline (8 levels) with a fixed 0–100% vertical scale.
pub fn sparkline_percent(values: &[f64], width: usize) -> String {
    const BLOCKS: [char; 8] = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];
    let width = width.max(1);
    if values.is_empty() {
        return "▁".repeat(width);
    }
    resample(values, width)
        .iter()
        .map(|v| {
            let pct = v.clamp(0.0, 100.0);
            let level = ((pct / 100.0) * 7.0).round() as usize;
            BLOCKS[level.min(7)]
        })
        .collect()
}

/// Min / max / latest over the visible (resampled) window.
pub fn window_stats(values: &[f64], width: usize) -> (f64, f64, f64) {
    let s = resample(values, width.max(1));
    if s.is_empty() {
        return (0.0, 0.0, 0.0);
    }
    let mut min = s[0];
    let mut max = s[0];
    for v in &s[1..] {
        min = min.min(*v);
        max = max.max(*v);
    }
    let latest = s[s.len() - 1];
    (min, max, latest)
}

pub fn bar_symbols() -> bar::Set {
    bar::NINE_LEVELS
}

pub fn push_history(history: &mut Vec<f64>, value: f64, max_len: usize) {
    let v = if value.is_finite() {
        value.clamp(0.0, 100.0)
    } else {
        0.0
    };
    history.push(v);
    if history.len() > max_len {
        let drain = history.len() - max_len;
        history.drain(0..drain);
    }
}

fn resample(values: &[f64], width: usize) -> Vec<f64> {
    if width == 0 {
        return Vec::new();
    }
    if values.is_empty() {
        return vec![0.0; width];
    }
    if values.len() <= width {
        let pad = width - values.len();
        let mut out = vec![0.0; pad];
        out.extend(values.iter().copied());
        return out;
    }
    let mut out = Vec::with_capacity(width);
    for i in 0..width {
        let start = i * values.len() / width;
        let end = ((i + 1) * values.len() / width).max(start + 1).min(values.len());
        let bucket_max = values[start..end]
            .iter()
            .copied()
            .fold(0.0_f64, f64::max);
        out.push(bucket_max);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_scale_shows_low_cpu_not_flat_top() {
        let steady = vec![5.0, 5.1, 4.9, 5.0];
        let s = sparkline_percent(&steady, 4);
        assert!(s.chars().all(|c| c == '▁' || c == '▂'),
            "steady ~5% should stay in lower blocks, got {}",
            s);
    }

    #[test]
    fn resample_preserves_spike() {
        let data = vec![0.0, 0.0, 100.0, 0.0, 0.0];
        let series = percent_series(&data, 3);
        assert!(series.contains(&100), "spike should survive downsampling: {:?}", series);
    }

    #[test]
    fn pads_left_when_short() {
        let series = percent_series(&[10.0, 20.0], 4);
        assert_eq!(series, vec![0, 0, 10, 20]);
    }

    #[test]
    fn empty_history_is_flat_baseline() {
        let s = sparkline_percent(&[], 5);
        assert_eq!(s, "▁▁▁▁▁");
    }

    #[test]
    fn window_stats_tracks_latest() {
        let (min, max, latest) = window_stats(&[1.0, 50.0, 25.0], 3);
        assert!((min - 1.0).abs() < 0.01);
        assert!((max - 50.0).abs() < 0.01);
        assert!((latest - 25.0).abs() < 0.01);
    }
}
