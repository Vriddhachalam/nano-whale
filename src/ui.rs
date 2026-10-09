use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Sparkline};
use ratatui::Frame;

use crate::chart::{bar_symbols, percent_series, sparkline_percent, window_stats};
use crate::config::Config;
use crate::model::{AppState, ContentTab, PanelFocus};
use crate::theme::{
    chart_frame_block, content_block, cpu_color, empty_list_line, footer_lines, mem_color,
    panel_block, screen_style, selection_style, tab_bar_block, tab_label, zebra_bg, RowContext,
};
use crate::textutil::strip_ansi;
use crate::theme::palette::*;

pub fn draw(frame: &mut Frame, state: &mut AppState, config: &Config) {
    let area = frame.area();
    frame.render_widget(Clear, area);
    frame.render_widget(Paragraph::new("").style(screen_style()), area);

    let footer_width = area.width.saturating_sub(2);
    let mut footer_text = footer_lines(
        footer_width,
        state.focus.label(),
        state.tab.glyph(),
        state.tab.title(),
        state.logs_auto_scroll && state.tab == ContentTab::Logs,
    );
    if state.select_mode {
        footer_text.insert(
            0,
            Line::from(Span::styled(
                " Select · drag the right pane · wheel extends · Esc done ",
                Style::default()
                    .fg(Color::Rgb(15, 23, 42))
                    .bg(WARN)
                    .add_modifier(Modifier::BOLD),
            )),
        );
    }
    let footer_h = (footer_text.len() as u16).max(1);

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(1),
            Constraint::Length(footer_h),
        ])
        .margin(1)
        .split(area);

    draw_top_bar(frame, rows[0], state);
    let left_pct = (rows[1].width as f32 * 0.42).max(32.0) as u16;
    let main = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(left_pct),
            Constraint::Length(1),
            Constraint::Min(12),
        ])
        .split(rows[1]);

    state.right_pane = Some((main[2].x, main[2].y, main[2].width, main[2].height));

    paint_panel_bg(frame, main[0], SURFACE);
    paint_panel_bg(frame, main[1], GUTTER);
    paint_panel_bg(frame, main[2], SURFACE_ALT);
    draw_right(frame, main[2], state, config);
    draw_gutter(frame, main[1]);
    draw_left(frame, main[0], state, config);

    let footer_area = rows[2];
    let footer = Paragraph::new(footer_text).style(
        Style::default()
            .fg(TEXT)
            .bg(SURFACE)
            .add_modifier(Modifier::BOLD),
    );
    frame.render_widget(footer, footer_area);
    // Paint any slack below the layout (resize leftovers) so ghosts don't linger.
    if footer_area.y + footer_area.height < area.height {
        let slack = Rect {
            x: area.x,
            y: footer_area.y + footer_area.height,
            width: area.width,
            height: area.height - footer_area.y - footer_area.height,
        };
        frame.render_widget(Clear, slack);
        frame.render_widget(Paragraph::new("").style(screen_style()), slack);
    }

    draw_notify(frame, area, state);
}

fn draw_gutter(frame: &mut Frame, area: Rect) {
    frame.render_widget(
        Block::default().style(Style::default().bg(GUTTER)),
        area,
    );
}

fn draw_top_bar(frame: &mut Frame, area: Rect, state: &AppState) {
    let running = state
        .containers
        .iter()
        .filter(|c| c.state == "running")
        .count();
    let total = state.containers.len();
    let line = Line::from(vec![
        Span::styled("  🐳 ", Style::default().fg(WHALE)),
        Span::styled(
            "nano-whale",
            Style::default().fg(ACCENT2).add_modifier(Modifier::BOLD),
        ),
        Span::styled(" v2 ", Style::default().fg(MUTED)),
        Span::styled("│ ", Style::default().fg(BORDER)),
        Span::styled(state.hostname.clone(), Style::default().fg(TEXT)),
        Span::styled(" │ ", Style::default().fg(BORDER)),
        badge("●", &format!("{}", running), SUCCESS),
        Span::styled(" running  ", Style::default().fg(MUTED)),
        badge("▣", &format!("{}", total), CONTAINERS),
        Span::styled(" ctr  ", Style::default().fg(MUTED)),
        badge("◫", &format!("{}", state.images.len()), IMAGES),
        Span::styled(" img  ", Style::default().fg(MUTED)),
        badge("▤", &format!("{}", state.volumes.len()), VOLUMES),
        Span::styled(" vol  ", Style::default().fg(MUTED)),
        badge("◎", &format!("{}", state.networks.len()), NETWORKS),
        Span::styled(" net", Style::default().fg(MUTED)),
    ]);
    let block = Block::default()
        .borders(Borders::BOTTOM)
        .border_style(Style::default().fg(BORDER_BRIGHT))
        .style(Style::default().bg(BG));
    frame.render_widget(Paragraph::new(line).block(block), area);
}

fn badge(icon: &str, value: &str, color: Color) -> Span<'static> {
    Span::styled(
        format!("{} {}", icon, value),
        Style::default().fg(color).add_modifier(Modifier::BOLD),
    )
}

fn draw_notify(frame: &mut Frame, area: Rect, state: &AppState) {
    let Some(n) = &state.notify else {
        return;
    };
    if std::time::Instant::now() >= n.until {
        return;
    }
    let text = format!(" {} ", n.text);
    let cols = text.chars().count() as u16;
    let w = (cols + 2).min(area.width.saturating_sub(4)).max(12);
    let popup = Rect {
        x: area.width.saturating_sub(w) / 2,
        y: area.height / 2,
        width: w,
        height: 3,
    };
    let accent = if n.is_error { DANGER } else { SUCCESS };
    let inner_cols = w.saturating_sub(2) as usize;
    let mut shown: String = text.chars().take(inner_cols).collect();
    while shown.chars().count() < inner_cols {
        shown.push(' ');
    }
    frame.render_widget(Clear, popup);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(ratatui::widgets::block::BorderType::Double)
        .border_style(Style::default().fg(accent))
        .style(Style::default().bg(SURFACE_ALT).fg(accent));
    frame.render_widget(
        Paragraph::new(shown)
            .block(block)
            .style(Style::default().fg(accent).add_modifier(Modifier::BOLD)),
        popup,
    );
}

fn draw_left(frame: &mut Frame, area: Rect, state: &AppState, config: &Config) {
    let slots = resource_slots(area);
    draw_container_list(frame, slots[0], state, config);
    draw_panel_gutter(frame, slots[1]);
    draw_image_list(frame, slots[2], state);
    draw_panel_gutter(frame, slots[3]);
    draw_volume_list(frame, slots[4], state);
    draw_panel_gutter(frame, slots[5]);
    draw_network_list(frame, slots[6], state);
}

/// Containers, images, volumes, networks. Each list keeps a floor tall enough for
/// its border plus at least two text rows, so volume names are not clipped away.
fn resource_slots(area: Rect) -> [Rect; 7] {
    let gutter = 1u16;
    let mut heights = [8u16, 6, 6, 5];
    let body = area.height.saturating_sub(gutter * 3);
    let floor_sum: u16 = heights.iter().sum();
    if body > floor_sum {
        let extra = body - floor_sum;
        heights[0] += extra / 2;
        heights[1] += extra / 5;
        heights[2] += extra / 5;
        heights[3] += extra - extra / 2 - extra / 5 - extra / 5;
    } else if body < floor_sum {
        let mut over = floor_sum.saturating_sub(body);
        for h in heights.iter_mut().rev() {
            let spare = h.saturating_sub(4);
            let cut = spare.min(over);
            *h -= cut;
            over -= cut;
        }
    }
    let mut y = area.y;
    let mut rects = [Rect::default(); 7];
    for i in 0..4 {
        let used = y.saturating_sub(area.y);
        let h = heights[i].min(area.height.saturating_sub(used));
        rects[i * 2] = Rect {
            x: area.x,
            y,
            width: area.width,
            height: h,
        };
        y = y.saturating_add(h);
        if i < 3 {
            let used = y.saturating_sub(area.y);
            let gh = gutter.min(area.height.saturating_sub(used));
            rects[i * 2 + 1] = Rect {
                x: area.x,
                y,
                width: area.width,
                height: gh,
            };
            y = y.saturating_add(gh);
        }
    }
    rects
}

fn draw_panel_gutter(frame: &mut Frame, area: Rect) {
    frame.render_widget(
        Paragraph::new("").style(Style::default().bg(GUTTER)),
        area,
    );
}

fn draw_container_list(frame: &mut Frame, area: Rect, state: &AppState, config: &Config) {
    let selective = state.containers.len() > config.stats_all_container_max;
    let focused = state.focus == PanelFocus::Containers;
    let panel_title = format!("Containers · {}", state.containers.len());
    let block = panel_block(
        &panel_title,
        CONTAINERS,
        focused,
        Some(PanelFocus::Containers.hotkey()),
    );
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(1)])
        .split(inner);
    let list_w = rows[1].width.max(1) as usize;
    let mut items: Vec<ListItem> = Vec::new();
    if state.containers.is_empty() {
        items.push(ListItem::new(empty_list_line("No containers found")));
    }

    items.extend(state.containers.iter().enumerate().map(|(i, c)| {
            let row = RowContext {
                selected: i == state.sel_container,
                panel_focused: focused,
            };
            let marked = state.marked_containers.contains(&c.name);
            let running = c.state == "running";
            let (dot, status_style) = if running {
                ("●", row.status_running(true))
            } else {
                ("○", row.muted_style())
            };
            let cpu_pct = if c.state == "running" {
                if selective && i != state.sel_container {
                    None
                } else {
                    Some(
                        state
                            .stats
                            .get(&c.name)
                            .map(|s| s.cpu_percent)
                            .unwrap_or(0.0),
                    )
                }
            } else {
                None
            };
            let name = truncate(&c.name, 16);
            let tail = if c.ports.is_empty() {
                truncate(&c.image, 10)
            } else {
                truncate(&c.ports, 10)
            };

            let mut spans = vec![
                Span::styled(if marked { "◆ " } else { "  " }, row.mark_style(marked)),
                Span::styled(format!("{} ", dot), status_style),
                Span::styled(format!("{:<16} ", name), row.name_style()),
            ];
            if let Some(pct) = cpu_pct {
                spans.push(Span::styled(
                    format!("{:>5.1}% ", pct),
                    row.cpu_style(pct),
                ));
            } else {
                spans.push(Span::styled("   —   ", row.muted_style()));
            }
            spans.push(Span::styled(tail, row.muted_style()));

            if row.selected && running && list_w >= 70 {
                if let Some(hist) = state.cpu_history.get(&c.name) {
                    let mini = sparkline_percent(hist, 8);
                    if !mini.is_empty() {
                        let pct = state
                            .stats
                            .get(&c.name)
                            .map(|s| s.cpu_percent)
                            .unwrap_or(0.0);
                        spans.push(Span::raw(" "));
                        spans.push(Span::styled(mini, row.cpu_style(pct)));
                    }
                }
            }

            let style = if row.selected {
                selection_style(focused)
            } else {
                Style::default().bg(zebra_bg(i))
            };
            ListItem::new(Line::from(fit_spans_width(spans, list_w.saturating_sub(1)))).style(style)
        }));

    frame.render_widget(
        Paragraph::new(Line::from(Span::styled(
            " M  ST  NAME              CPU   PORTS",
            Style::default().fg(MUTED).add_modifier(Modifier::DIM),
        ))),
        rows[0],
    );
    paint_panel_bg(frame, rows[1], SURFACE);
    render_scrollable_list(frame, rows[1], items, state.sel_container);
}

fn draw_image_list(frame: &mut Frame, area: Rect, state: &AppState) {
    let focused = state.focus == PanelFocus::Images;
    let mut collected: Vec<ListItem> = Vec::new();
    if state.images.is_empty() {
        collected.push(ListItem::new(empty_list_line("No images")));
    }
    let title = format!("Images · {}", state.images.len());
    let block = panel_block(&title, IMAGES, focused, Some(PanelFocus::Images.hotkey()));
    let inner = block.inner(area);
    let list_w = inner.width.max(1) as usize;
    collected.extend(state.images.iter().enumerate().map(|(i, img)| {
        let row = RowContext {
            selected: i == state.sel_image,
            panel_focused: focused,
        };
        let marked = state.marked_images.contains(&img.id);
        let label = truncate(&format!("{}:{}", img.repo, img.tag), list_w.saturating_sub(10));
        let spans = vec![
            Span::styled(if marked { "◆ " } else { "  " }, row.mark_style(marked)),
            Span::styled(format!("{label} "), row.name_style()),
            Span::styled(img.size.clone(), row.muted_style()),
        ];
        ListItem::new(Line::from(fit_spans_width(spans, list_w.saturating_sub(1))))
            .style(list_row_style(i, state.sel_image, focused))
    }));
    frame.render_widget(block, area);
    paint_panel_bg(frame, inner, SURFACE);
    render_scrollable_list(frame, inner, collected, state.sel_image);
}

fn draw_volume_list(frame: &mut Frame, area: Rect, state: &AppState) {
    let focused = state.focus == PanelFocus::Volumes;
    let mut collected: Vec<ListItem> = Vec::new();
    if state.volumes.is_empty() {
        collected.push(ListItem::new(empty_list_line("No volumes")));
    }
    let title = format!("Volumes · {}", state.volumes.len());
    let block = panel_block(&title, VOLUMES, focused, Some(PanelFocus::Volumes.hotkey()));
    let inner = block.inner(area);
    let list_w = inner.width.max(1) as usize;
    collected.extend(state.volumes.iter().enumerate().map(|(i, v)| {
        let row = RowContext {
            selected: i == state.sel_volume,
            panel_focused: focused,
        };
        let marked = state.marked_volumes.contains(&v.name);
        let label = truncate(&v.name, list_w.saturating_sub(12).max(8));
        let spans = vec![
            Span::styled(if marked { "◆ " } else { "  " }, row.mark_style(marked)),
            Span::styled(format!("{label} "), row.name_style()),
            Span::styled(v.driver.clone(), row.muted_style()),
        ];
        ListItem::new(Line::from(fit_spans_width(spans, list_w.saturating_sub(1))))
            .style(list_row_style(i, state.sel_volume, focused))
    }));
    frame.render_widget(block, area);
    paint_panel_bg(frame, inner, SURFACE);
    render_scrollable_list(frame, inner, collected, state.sel_volume);
}

fn draw_network_list(frame: &mut Frame, area: Rect, state: &AppState) {
    let focused = state.focus == PanelFocus::Networks;
    let mut collected: Vec<ListItem> = Vec::new();
    if state.networks.is_empty() {
        collected.push(ListItem::new(empty_list_line("No networks")));
    }
    let title = format!("Networks · {}", state.networks.len());
    let block = panel_block(&title, NETWORKS, focused, Some(PanelFocus::Networks.hotkey()));
    let inner = block.inner(area);
    let list_w = inner.width.max(1) as usize;
    collected.extend(state.networks.iter().enumerate().map(|(i, n)| {
        let row = RowContext {
            selected: i == state.sel_network,
            panel_focused: focused,
        };
        let label = truncate(&n.name, list_w.saturating_sub(12).max(8));
        let spans = vec![
            Span::styled("  ", row.muted_style()),
            Span::styled(format!("{label} "), row.name_style()),
            Span::styled(n.driver.clone(), row.muted_style()),
        ];
        ListItem::new(Line::from(fit_spans_width(spans, list_w.saturating_sub(1))))
            .style(list_row_style(i, state.sel_network, focused))
    }));
    frame.render_widget(block, area);
    paint_panel_bg(frame, inner, SURFACE);
    render_scrollable_list(frame, inner, collected, state.sel_network);
}

fn render_scrollable_list(frame: &mut Frame, area: Rect, items: Vec<ListItem>, selected: usize) {
    if area.width == 0 || area.height == 0 || items.is_empty() {
        return;
    }
    let idx = selected.min(items.len().saturating_sub(1));
    let visible = area.height.max(1) as usize;
    let offset = (idx + 1).saturating_sub(visible);
    let mut list_state = ListState::default()
        .with_offset(offset)
        .with_selected(Some(idx));
    frame.render_stateful_widget(List::new(items), area, &mut list_state);
}

fn list_row_style(index: usize, selected: usize, focused: bool) -> Style {
    if index == selected {
        selection_style(focused)
    } else {
        Style::default().bg(zebra_bg(index))
    }
}

fn draw_right(frame: &mut Frame, area: Rect, state: &mut AppState, config: &Config) {
    state.pane_body = None;
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(3)])
        .split(area);

    let tab_line = Line::from(
        [
            ContentTab::Logs,
            ContentTab::Stats,
            ContentTab::Env,
            ContentTab::Config,
            ContentTab::Top,
        ]
        .iter()
        .enumerate()
        .flat_map(|(i, t)| {
            let mut spans = vec![tab_label(t.glyph(), t.title(), *t == state.tab)];
            if i < 4 {
                spans.push(Span::styled("│", Style::default().fg(BORDER)));
            }
            spans
        })
        .collect::<Vec<_>>(),
    );
    frame.render_widget(
        Paragraph::new(tab_line).block(tab_bar_block()),
        chunks[0],
    );

    let pane_title = truncate(
        &content_pane_title(state),
        chunks[1].width.saturating_sub(6) as usize,
    );
    let block = content_block(&pane_title, None);

    match state.tab {
        ContentTab::Stats => {
            draw_stats_tab(frame, chunks[1], state, config, block);
        }
        ContentTab::Logs => {
            draw_logs_pane(frame, chunks[1], block, state);
        }
        _ => {
            let body = content_plain(state);
            draw_text_pane(frame, chunks[1], block, body, state, state.content_scroll);
        }
    }
}

fn content_pane_title(state: &AppState) -> String {
    let name = state
        .selected_container()
        .map(|c| c.name.as_str())
        .unwrap_or("—");
    match state.tab {
        ContentTab::Logs => format!("Logs · {}", name),
        ContentTab::Stats => format!("Stats · {}", name),
        ContentTab::Env => format!("Environment · {}", name),
        ContentTab::Config => format!("Config · {}", name),
        ContentTab::Top => format!("Processes · {}", name),
    }
}

fn content_plain(state: &AppState) -> String {
    match state.tab {
        ContentTab::Logs => {
            if state.logs.is_empty() {
                "Fetching container logs…".into()
            } else {
                state.logs.clone()
            }
        }
        ContentTab::Env => {
            if state.detail_loading {
                "Loading environment variables…".into()
            } else if state.env_text.is_empty() {
                "No environment data.".into()
            } else {
                state.env_text.clone()
            }
        }
        ContentTab::Config => {
            if state.detail_loading {
                "Loading inspect data…".into()
            } else {
                state.config_text.clone()
            }
        }
        ContentTab::Top => {
            if state.detail_loading {
                "Loading process list…".into()
            } else {
                state.top_text.clone()
            }
        }
        ContentTab::Stats => String::new(),
    }
}

fn draw_stats_tab(
    frame: &mut Frame,
    area: Rect,
    state: &AppState,
    config: &Config,
    block: Block<'_>,
) {
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.width < 4 || inner.height < 8 {
        return;
    }

    let c = state.selected_container();
    if c.is_none() {
        frame.render_widget(
            Paragraph::new("Select a container to view stats").style(
                Style::default().fg(MUTED).add_modifier(Modifier::ITALIC),
            ),
            inner,
        );
        return;
    }
    let c = c.unwrap();
    if c.state != "running" {
        let lines = vec![
            Line::from(Span::styled(
                c.name.clone(),
                Style::default().fg(ACCENT2).add_modifier(Modifier::BOLD),
            )),
            Line::from(""),
            Line::from(Span::styled("Container is not running", Style::default().fg(WARN))),
            Line::from(Span::styled("Press s to start", Style::default().fg(MUTED))),
        ];
        frame.render_widget(Paragraph::new(lines), inner);
        return;
    }

    let snap = state.stats.get(&c.name);
    let cpu_hist = state.cpu_history.get(&c.name).map(|v| v.as_slice()).unwrap_or(&[]);
    let mem_hist = state.mem_history.get(&c.name).map(|v| v.as_slice()).unwrap_or(&[]);
    let cpu = snap.map(|s| s.cpu_percent).unwrap_or(0.0);
    let mem = snap.map(|s| s.mem_percent).unwrap_or(0.0);

    let chart_w = (inner.width as usize).min(config.chart_width).clamp(8, 160);

    let (cpu_min, cpu_max, _) = window_stats(cpu_hist, chart_w);
    let (mem_min, mem_max, _) = window_stats(mem_hist, chart_w);
    let cpu_data = percent_series(cpu_hist, chart_w);
    let mem_data = percent_series(mem_hist, chart_w);

    let layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(1),
            Constraint::Length(4),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(4),
            Constraint::Length(1),
            Constraint::Min(2),
        ])
        .split(inner);

    let meta = vec![
        Line::from(vec![
            Span::styled("Container  ", Style::default().fg(MUTED)),
            Span::styled(
                c.name.clone(),
                Style::default().fg(WHALE).add_modifier(Modifier::BOLD),
            ),
        ]),
        Line::from(vec![
            Span::styled("ID  ", Style::default().fg(MUTED)),
            Span::styled(
                c.id.chars().take(12).collect::<String>(),
                Style::default().fg(TEXT),
            ),
            Span::styled("   │   ", Style::default().fg(BORDER)),
            Span::styled("Now  ", Style::default().fg(MUTED)),
            Span::styled(
                format!("CPU {:.1}%  MEM {:.1}%", cpu, mem),
                Style::default().fg(ACCENT2),
            ),
        ]),
    ];
    frame.render_widget(Paragraph::new(meta), layout[0]);

    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled("CPU ", Style::default().fg(ACCENT).add_modifier(Modifier::BOLD)),
            Span::styled(
                format!("{:.1}%", cpu),
                Style::default().fg(cpu_color(cpu)).add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                format!("   window {:.1}% – {:.1}%", cpu_min, cpu_max),
                Style::default().fg(MUTED),
            ),
        ])),
        layout[1],
    );

    let cpu_block = chart_frame_block("CPU history");
    let cpu_inner = cpu_block.inner(layout[2]);
    frame.render_widget(cpu_block, layout[2]);
    let cpu_chart = Sparkline::default()
        .data(&cpu_data)
        .max(100)
        .bar_set(bar_symbols())
        .style(Style::default().fg(cpu_color(cpu)).bg(Color::Rgb(18, 26, 42)));
    frame.render_widget(cpu_chart, cpu_inner);

    frame.render_widget(Paragraph::new(scale_axis_line(layout[3].width)), layout[3]);

    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled("MEM ", Style::default().fg(ACCENT).add_modifier(Modifier::BOLD)),
            Span::styled(
                format!("{:.1}%", mem),
                Style::default().fg(mem_color(mem)).add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                format!(
                    "   ({})   window {:.1}% – {:.1}%",
                    snap.map(|s| s.mem_usage.as_str()).unwrap_or("N/A"),
                    mem_min,
                    mem_max
                ),
                Style::default().fg(MUTED),
            ),
        ])),
        layout[4],
    );

    let mem_block = chart_frame_block("Memory history");
    let mem_inner = mem_block.inner(layout[5]);
    frame.render_widget(mem_block, layout[5]);
    let mem_chart = Sparkline::default()
        .data(&mem_data)
        .max(100)
        .bar_set(bar_symbols())
        .style(Style::default().fg(mem_color(mem)).bg(Color::Rgb(18, 26, 42)));
    frame.render_widget(mem_chart, mem_inner);

    frame.render_widget(Paragraph::new(scale_axis_line(layout[6].width)), layout[6]);

    let mut footer = vec![
        Line::from(vec![
            Span::styled("PIDs    ", Style::default().fg(MUTED)),
            Span::styled(
                snap.map(|s| s.pids.clone()).unwrap_or_else(|| "N/A".into()),
                Style::default().fg(TEXT),
            ),
            Span::styled("   │   ", Style::default().fg(BORDER)),
            Span::styled("Net I/O ", Style::default().fg(MUTED)),
            Span::styled(
                snap.map(|s| s.net_io.clone()).unwrap_or_else(|| "N/A".into()),
                Style::default().fg(TEXT),
            ),
        ]),
    ];
    let block_io = snap.map(|s| s.block_io.as_str()).unwrap_or("N/A");
    if block_io != "N/A" {
        footer.push(Line::from(vec![
            Span::styled("Block   ", Style::default().fg(MUTED)),
            Span::styled(block_io.to_string(), Style::default().fg(TEXT)),
        ]));
    }
    frame.render_widget(Paragraph::new(footer), layout[7]);
}

fn scale_axis_line(width: u16) -> Line<'static> {
    let dash_len = width.saturating_sub(8) as usize;
    Line::from(vec![
        Span::styled("0%", Style::default().fg(MUTED)),
        Span::raw(" "),
        Span::styled("─".repeat(dash_len.max(1)), Style::default().fg(BORDER)),
        Span::raw(" "),
        Span::styled("100%", Style::default().fg(MUTED)),
    ])
}

fn draw_logs_pane(frame: &mut Frame, area: Rect, block: Block<'_>, state: &mut AppState) {
    let inner = block.inner(area);
    frame.render_widget(block, area);
    paint_panel_bg(frame, inner, SURFACE_ALT);

    let show_find = state.find_editing || !state.find_query.is_empty();
    let (body, prompt) = if show_find && inner.height > 1 {
        let parts = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(1), Constraint::Length(1)])
            .split(inner);
        (parts[0], Some(parts[1]))
    } else {
        (inner, None)
    };
    state.log_view_rows = body.height.max(1);

    let raw = if state.logs.is_empty() {
        "Streaming logs…\n\nMouse wheel scrolls this pane · / find · l opens logs in the terminal"
            .to_string()
    } else {
        state.logs.clone()
    };
    let query = if state.logs.is_empty() {
        ""
    } else {
        state.find_query.trim()
    };
    let selection = drag_range(state);
    let lines = styled_log_lines(&raw, body.width, query, selection);
    let style = if state.logs.is_empty() {
        Style::default().fg(MUTED).add_modifier(Modifier::ITALIC)
    } else {
        Style::default()
    };
    let scroll_y = log_scroll_y_count(
        lines.len(),
        body.height,
        state.logs_auto_scroll,
        state.content_scroll,
    );
    state.pane_body = Some((body.x, body.y, body.width, body.height));
    state.pane_scroll = scroll_y;
    frame.render_widget(
        Paragraph::new(lines).style(style).scroll((scroll_y, 0)),
        body,
    );
    if let Some(prompt) = prompt {
        let cursor = if state.find_editing { "▌" } else { "" };
        frame.render_widget(
            Paragraph::new(format!(
                " Find: {}{cursor}   Esc exit   n next",
                state.find_query
            ))
            .style(
                Style::default()
                    .fg(ACCENT2)
                    .bg(SURFACE)
                    .add_modifier(Modifier::BOLD),
            ),
            prompt,
        );
    }
}

fn draw_text_pane(
    frame: &mut Frame,
    area: Rect,
    block: Block<'_>,
    body: String,
    state: &mut AppState,
    scroll: u16,
) {
    let inner = block.inner(area);
    frame.render_widget(block, area);
    paint_panel_bg(frame, inner, SURFACE_ALT);
    let lines = styled_log_lines(&body, inner.width, "", drag_range(state));
    state.pane_body = Some((inner.x, inner.y, inner.width, inner.height));
    state.pane_scroll = scroll;
    frame.render_widget(Paragraph::new(lines).scroll((scroll, 0)), inner);
}

fn drag_range(state: &AppState) -> Option<(usize, usize)> {
    match (state.drag_from, state.drag_to) {
        (Some(a), Some(b)) => Some((a.min(b), a.max(b))),
        _ => None,
    }
}

fn paint_panel_bg(frame: &mut Frame, area: Rect, bg: Color) {
    if area.width == 0 || area.height == 0 {
        return;
    }
    frame.render_widget(Clear, area);
    frame.render_widget(Paragraph::new("").style(Style::default().bg(bg)), area);
}

fn styled_log_lines(
    text: &str,
    width: u16,
    query: &str,
    selected: Option<(usize, usize)>,
) -> Vec<Line<'static>> {
    let max = width.max(1) as usize;
    text.lines()
        .enumerate()
        .map(|(i, line)| {
            let on = selected.is_some_and(|(a, b)| i >= a && i <= b);
            highlight_clipped(&strip_ansi(line), max, query, on)
        })
        .collect()
}

fn highlight_clipped(line: &str, max_chars: usize, query: &str, selected: bool) -> Line<'static> {
    let normal = if selected {
        Style::default().fg(TEXT).bg(SELECT_BG)
    } else {
        Style::default().fg(LOG_TEXT)
    };
    let hit = Style::default()
        .fg(Color::Rgb(15, 23, 42))
        .bg(WARN)
        .add_modifier(Modifier::BOLD);
    let chars: Vec<char> = line.chars().collect();
    let qlen = query.chars().count();
    let mut spans: Vec<Span<'static>> = Vec::new();
    let mut i = 0;
    let mut used = 0;
    while i < chars.len() && used < max_chars {
        let matched = qlen > 0 && starts_with_ignore_ascii(&chars[i..], query);
        if matched {
            let take = qlen.min(max_chars - used);
            let text: String = chars[i..i + take].iter().collect();
            spans.push(Span::styled(text, hit));
            i += take;
            used += take;
        } else {
            let mut end = i + 1;
            while end < chars.len() && used + (end - i) < max_chars {
                if qlen > 0 && starts_with_ignore_ascii(&chars[end..], query) {
                    break;
                }
                end += 1;
            }
            let take = (end - i).min(max_chars - used);
            let text: String = chars[i..i + take].iter().collect();
            spans.push(Span::styled(text, normal));
            i += take;
            used += take;
        }
    }
    if i < chars.len() && max_chars > 0 {
        if let Some(last) = spans.last_mut() {
            let trimmed: String = last
                .content
                .chars()
                .take(last.content.chars().count().saturating_sub(1))
                .chain(['…'])
                .collect();
            let style = last.style;
            *last = Span::styled(trimmed, style);
        }
    }
    if spans.is_empty() {
        spans.push(Span::styled(" ", normal));
    }
    Line::from(spans)
}

fn starts_with_ignore_ascii(chars: &[char], query: &str) -> bool {
    let mut rest = chars.iter();
    for qc in query.chars() {
        match rest.next() {
            Some(c) if c.eq_ignore_ascii_case(&qc) => {}
            _ => return false,
        }
    }
    !query.is_empty()
}

fn log_scroll_y_count(line_count: usize, height: u16, auto: bool, manual: u16) -> u16 {
    if auto {
        let visible = height.max(1) as usize;
        line_count.max(1).saturating_sub(visible) as u16
    } else {
        manual
    }
}

fn spans_width(spans: &[Span<'_>]) -> usize {
    spans.iter().map(|s| s.content.chars().count()).sum()
}

fn fit_spans_width(spans: Vec<Span<'_>>, max: usize) -> Vec<Span<'_>> {
    let mut out = spans;
    while spans_width(&out) > max && out.len() > 1 {
        out.pop();
    }
    if spans_width(&out) > max {
        if let Some(last) = out.last_mut() {
            let overflow = spans_width(&out) - max;
            let n = last.content.chars().count();
            if n > overflow {
                let trimmed: String = last.content.chars().take(n - overflow).collect();
                *last = Span::styled(trimmed, last.style);
            } else {
                out.pop();
            }
        }
    }
    out
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        s.chars().take(max.saturating_sub(1)).chain(['…']).collect()
    }
}
