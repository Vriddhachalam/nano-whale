use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::block::BorderType;
use ratatui::widgets::{Block, Borders, Padding};

/// Palette tuned for dark terminals (Docker / ocean vibe).
pub mod palette {
    use ratatui::style::Color;

    pub const BG: Color = Color::Rgb(12, 18, 32);
    pub const SURFACE: Color = Color::Rgb(22, 30, 48);
    pub const SURFACE_ALT: Color = Color::Rgb(30, 41, 59);
    pub const SURFACE_ZEBRA: Color = Color::Rgb(26, 35, 54);
    pub const BORDER: Color = Color::Rgb(51, 65, 85);
    pub const BORDER_BRIGHT: Color = Color::Rgb(94, 234, 212);
    pub const GUTTER: Color = Color::Rgb(18, 25, 40);
    pub const TEXT: Color = Color::Rgb(226, 232, 240);
    pub const MUTED: Color = Color::Rgb(148, 163, 184);
    pub const ACCENT: Color = Color::Rgb(56, 189, 248);
    pub const ACCENT2: Color = Color::Rgb(34, 211, 238);
    pub const WHALE: Color = Color::Rgb(125, 211, 252);
    pub const SUCCESS: Color = Color::Rgb(74, 222, 128);
    pub const WARN: Color = Color::Rgb(250, 204, 21);
    pub const DANGER: Color = Color::Rgb(248, 113, 113);
    pub const MARK: Color = Color::Rgb(251, 191, 36);
    pub const CONTAINERS: Color = Color::Rgb(52, 211, 153);
    pub const IMAGES: Color = Color::Rgb(251, 191, 36);
    pub const VOLUMES: Color = Color::Rgb(192, 132, 252);
    pub const NETWORKS: Color = Color::Rgb(96, 165, 250);
    pub const LOG_TEXT: Color = Color::Rgb(203, 213, 225);
    pub const SELECT_BG: Color = Color::Rgb(25, 55, 88);
    pub const SELECT_BG_DIM: Color = Color::Rgb(35, 48, 68);
}

use palette::*;

pub fn screen_style() -> Style {
    Style::default().bg(BG).fg(TEXT)
}

pub fn panel_block<'a>(title: &'a str, accent: Color, focused: bool, hotkey: Option<char>) -> Block<'a> {
    let border = if focused {
        BORDER_BRIGHT
    } else {
        accent
    };
    let title_text = if let Some(k) = hotkey {
        format!(" [{}] {} ", k, title)
    } else {
        format!(" {} ", title)
    };
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border))
        .title(Span::styled(
            title_text,
            Style::default()
                .fg(if focused { BORDER_BRIGHT } else { TEXT })
                .add_modifier(Modifier::BOLD),
        ))
        .padding(Padding::new(1, 1, 0, 0))
        .style(Style::default().bg(SURFACE))
}

pub fn chart_frame_block<'a>(label: &'a str) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER))
        .title(Span::styled(
            format!(" {} ", label),
            Style::default().fg(MUTED),
        ))
        .style(Style::default().bg(Color::Rgb(18, 26, 42)))
}

pub fn content_block<'a>(title: &'a str, subtitle: Option<&str>) -> Block<'a> {
    let title_line = if let Some(sub) = subtitle {
        format!(" {}  ·  {} ", title, sub)
    } else {
        format!(" {} ", title)
    };
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(ACCENT))
        .title(Span::styled(
            title_line,
            Style::default().fg(ACCENT2).add_modifier(Modifier::BOLD),
        ))
        .padding(Padding::new(1, 1, 0, 0))
        .style(Style::default().bg(SURFACE_ALT))
}

pub fn tab_bar_block() -> Block<'static> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER))
        .style(Style::default().bg(SURFACE))
        .padding(Padding::new(1, 1, 0, 0))
}

pub fn selection_style(focused: bool) -> Style {
    if focused {
        Style::default()
            .bg(SELECT_BG)
            .fg(TEXT)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default()
            .bg(SELECT_BG_DIM)
            .fg(TEXT)
    }
}

/// Per-cell foreground when a list row may be selected (span fg overrides list item style).
#[derive(Clone, Copy)]
pub struct RowContext {
    pub selected: bool,
    pub panel_focused: bool,
}

impl RowContext {
    pub fn name_style(self) -> Style {
        if self.selected && self.panel_focused {
            Style::default().fg(TEXT).add_modifier(Modifier::BOLD)
        } else if self.selected {
            Style::default().fg(ACCENT2).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(TEXT)
        }
    }

    pub fn muted_style(self) -> Style {
        let fg = if self.selected && self.panel_focused {
            Color::Rgb(186, 198, 214)
        } else {
            MUTED
        };
        Style::default().fg(fg)
    }

    pub fn mark_style(self, marked: bool) -> Style {
        if !marked {
            return Style::default().fg(if self.selected && self.panel_focused {
                SELECT_BG
            } else {
                SURFACE
            });
        }
        Style::default().fg(MARK).add_modifier(Modifier::BOLD)
    }

    pub fn status_running(self, running: bool) -> Style {
        if running {
            Style::default()
                .fg(if self.selected && self.panel_focused {
                    Color::Rgb(134, 239, 172)
                } else {
                    SUCCESS
                })
                .add_modifier(Modifier::BOLD)
        } else {
            self.muted_style()
        }
    }

    pub fn cpu_style(self, pct: f64) -> Style {
        if self.selected && self.panel_focused {
            let fg = if pct >= 80.0 {
                Color::Rgb(254, 202, 202)
            } else if pct >= 50.0 {
                Color::Rgb(253, 224, 71)
            } else if pct > 0.0 {
                Color::Rgb(167, 243, 208)
            } else {
                Color::Rgb(186, 198, 214)
            };
            Style::default().fg(fg).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(cpu_color(pct))
        }
    }
}

pub fn zebra_bg(index: usize) -> Color {
    if index.is_multiple_of(2) {
        SURFACE
    } else {
        SURFACE_ZEBRA
    }
}

pub fn cpu_color(pct: f64) -> Color {
    if pct >= 80.0 {
        DANGER
    } else if pct >= 50.0 {
        WARN
    } else if pct > 0.0 {
        SUCCESS
    } else {
        MUTED
    }
}

pub fn mem_color(pct: f64) -> Color {
    if pct >= 90.0 {
        DANGER
    } else if pct >= 70.0 {
        WARN
    } else if pct > 0.0 {
        ACCENT2
    } else {
        MUTED
    }
}

pub fn key_hint(key: &str, label: &str) -> Vec<Span<'static>> {
    vec![
        Span::styled(
            key.to_string(),
            Style::default().fg(ACCENT2).add_modifier(Modifier::BOLD),
        ),
        Span::styled(format!(" {}  ", label), Style::default().fg(MUTED)),
    ]
}

pub fn footer_lines(
    width: u16,
    focus_label: &str,
    tab_glyph: &str,
    tab_title: &str,
    logs_auto: bool,
) -> Vec<Line<'static>> {
    let width = width.max(1) as usize;
    let hints: &[(&str, &str)] = &[
        ("↑↓", "select"),
        ("←→", "tabs"),
        ("Tab", "panel"),
        ("2", "containers"),
        ("3", "images"),
        ("4", "volumes"),
        ("5", "networks"),
        ("v", "copy"),
        ("l", "logs"),
        ("/", "find"),
        ("Esc", "exit find"),
        ("n", "next"),
        ("t", "shell"),
        ("Home", "top"),
        ("End", "tail"),
        ("a", "follow"),
        ("s", "toggle"),
        ("r", "restart"),
        ("d", "delete"),
        ("m", "mark"),
        ("q", "quit"),
    ];

    let mut prefix = vec![
        Span::styled(
            " nano-whale ",
            Style::default().fg(WHALE).add_modifier(Modifier::BOLD),
        ),
        Span::styled("│", Style::default().fg(BORDER)),
        Span::styled(
            format!(" {focus_label} "),
            Style::default().fg(CONTAINERS),
        ),
        Span::styled("│", Style::default().fg(BORDER)),
        Span::styled(
            format!(" {tab_glyph} {tab_title} "),
            Style::default().fg(ACCENT2),
        ),
    ];
    if logs_auto {
        prefix.push(Span::styled("│", Style::default().fg(BORDER)));
        prefix.push(Span::styled(" ↓ auto ", Style::default().fg(SUCCESS)));
    }
    prefix.push(Span::styled(" │ ", Style::default().fg(BORDER)));

    let mut lines: Vec<Vec<Span<'static>>> = vec![prefix];
    for (key, label) in hints {
        let hint = key_hint(key, label);
        let hint_w = span_width(&hint);
        let used = span_width(lines.last().unwrap());
        if used > 0 && used + hint_w > width {
            lines.push(Vec::new());
        }
        lines.last_mut().unwrap().extend(hint);
    }
    lines
        .into_iter()
        .filter(|spans| !spans.is_empty())
        .map(Line::from)
        .collect()
}

fn span_width(spans: &[Span<'_>]) -> usize {
    spans.iter().map(|s| s.content.chars().count()).sum()
}

pub fn tab_label(glyph: &str, tab: &str, active: bool) -> Span<'static> {
    if active {
        Span::styled(
            format!(" {} {} ", glyph, tab),
            Style::default()
                .fg(Color::Rgb(15, 23, 42))
                .bg(ACCENT2)
                .add_modifier(Modifier::BOLD),
        )
    } else {
        Span::styled(
            format!(" {} {} ", glyph, tab),
            Style::default().fg(MUTED),
        )
    }
}

pub fn empty_list_line(message: &str) -> Line<'static> {
    Line::from(Span::styled(
        format!("  {} ", message),
        Style::default().fg(MUTED).add_modifier(Modifier::ITALIC),
    ))
}
