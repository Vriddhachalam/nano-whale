use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use anyhow::Context;
use crossterm::cursor::{Hide, MoveTo, Show};
use crossterm::event::{self, Event, KeyCode, KeyEventKind, MouseEventKind};
use crossterm::style::Print;
use crossterm::terminal::{self, Clear, ClearType, disable_raw_mode, enable_raw_mode};
use crossterm::{queue, ExecutableCommand};

use crate::textutil::strip_ansi;

/// Follow container logs on the real terminal, with `/` search.
pub fn run(name: &str, tail: usize) -> anyhow::Result<()> {
    let mut child = Command::new("docker")
        .env("DOCKER_CLI_HINTS", "false")
        .args(["logs", "-f", "--tail", &tail.to_string(), name])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("docker logs")?;

    let (tx, rx) = mpsc::channel::<String>();
    if let Some(out) = child.stdout.take() {
        let tx = tx.clone();
        thread::spawn(move || {
            for line in BufReader::new(out).lines() {
                let Ok(line) = line else { break };
                if tx.send(line).is_err() {
                    break;
                }
            }
        });
    }
    if let Some(err) = child.stderr.take() {
        thread::spawn(move || {
            for line in BufReader::new(err).lines() {
                let Ok(line) = line else { break };
                if tx.send(line).is_err() {
                    break;
                }
            }
        });
    }

    enable_raw_mode()?;
    let _ = std::io::stdout().execute(crossterm::event::EnableMouseCapture);
    let _child = KillChild(child);
    let mut stdout = std::io::stdout();
    let _ = queue!(stdout, Hide);
    let mut lines: Vec<String> = Vec::new();
    let mut follow = true;
    let mut offset = 0usize;
    let mut query = String::new();
    let mut editing = false;
    let mut find_at: Option<usize> = None;
    let mut dirty = true;

    let result = loop {
        while let Ok(line) = rx.try_recv() {
            lines.push(strip_ansi(&line));
            if lines.len() > 8000 {
                let drop_n = lines.len() - 8000;
                lines.drain(0..drop_n);
                if let Some(at) = find_at.as_mut() {
                    *at = at.saturating_sub(drop_n);
                }
                offset = offset.saturating_sub(drop_n);
            }
            clamp_offset(lines.len(), &mut offset, follow);
            dirty = true;
        }

        if dirty {
            draw(
                &mut stdout,
                name,
                &lines,
                follow,
                offset,
                &query,
                editing,
            )?;
            dirty = false;
        }

        if !event::poll(Duration::from_millis(40))? {
            continue;
        }
        let Ok(event) = event::read() else {
            continue;
        };
        let Event::Key(key) = event else {
            if let Event::Mouse(mouse) = event {
                match mouse.kind {
                    MouseEventKind::ScrollUp => {
                        leave_follow(&lines, &mut follow, &mut offset);
                        offset = offset.saturating_sub(3);
                        clamp_offset(lines.len(), &mut offset, follow);
                    }
                    MouseEventKind::ScrollDown => {
                        leave_follow(&lines, &mut follow, &mut offset);
                        offset = offset.saturating_add(3);
                        clamp_offset(lines.len(), &mut offset, follow);
                    }
                    _ => {}
                }
                dirty = true;
            }
            continue;
        };
        if key.kind != KeyEventKind::Press {
            continue;
        }
        dirty = true;

        if super::is_ctrl_d(key) {
            break Ok(());
        }

        if editing {
            match key.code {
                KeyCode::Esc => {
                    editing = false;
                    query.clear();
                    find_at = None;
                }
                KeyCode::Enter => {
                    editing = false;
                    find_at = None;
                    jump_find(&lines, &query, true, &mut find_at, &mut offset, &mut follow);
                }
                KeyCode::Backspace => {
                    query.pop();
                }
                KeyCode::Char(c) => query.push(c),
                _ => {}
            }
            continue;
        }

        match key.code {
            KeyCode::Char('/') => editing = true,
            KeyCode::Char('n') => {
                jump_find(&lines, &query, true, &mut find_at, &mut offset, &mut follow);
            }
            KeyCode::Char('N') => {
                jump_find(&lines, &query, false, &mut find_at, &mut offset, &mut follow);
            }
            KeyCode::Esc => {
                query.clear();
                find_at = None;
            }
            KeyCode::Up => {
                leave_follow(&lines, &mut follow, &mut offset);
                offset = offset.saturating_sub(1);
                clamp_offset(lines.len(), &mut offset, follow);
            }
            KeyCode::Down => {
                leave_follow(&lines, &mut follow, &mut offset);
                offset = offset.saturating_add(1);
                clamp_offset(lines.len(), &mut offset, follow);
            }
            KeyCode::Home => {
                follow = false;
                offset = 0;
            }
            KeyCode::End => follow = true,
            _ => {}
        }
    };

    let _ = std::io::stdout().execute(crossterm::event::DisableMouseCapture);
    let _ = queue!(stdout, Show, Clear(ClearType::All));
    let _ = stdout.flush();
    disable_raw_mode().ok();
    result
}

fn clamp_offset(lines: usize, offset: &mut usize, follow: bool) {
    if follow {
        return;
    }
    let view = view_rows().max(1);
    *offset = (*offset).min(lines.saturating_sub(view));
}

struct KillChild(std::process::Child);

impl Drop for KillChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn leave_follow(lines: &[String], follow: &mut bool, offset: &mut usize) {
    if *follow {
        let view = view_rows().max(1);
        *offset = lines.len().saturating_sub(view);
        *follow = false;
    }
}

fn view_rows() -> usize {
    terminal::size().map(|(_, rows)| rows.saturating_sub(2) as usize).unwrap_or(20)
}

fn jump_find(
    lines: &[String],
    query: &str,
    forward: bool,
    find_at: &mut Option<usize>,
    offset: &mut usize,
    follow: &mut bool,
) {
    let q = query.trim();
    if q.is_empty() || lines.is_empty() {
        return;
    }
    let n = lines.len();
    let start = match *find_at {
        Some(i) if forward => (i + 1) % n,
        Some(i) => (i + n - 1) % n,
        None => 0,
    };
    let mut i = start;
    for _ in 0..n {
        if contains_ignore_ascii(&lines[i], q) {
            *follow = false;
            *offset = i;
            *find_at = Some(i);
            return;
        }
        i = if forward { (i + 1) % n } else { (i + n - 1) % n };
    }
}

fn draw(
    stdout: &mut std::io::Stdout,
    name: &str,
    lines: &[String],
    follow: bool,
    offset: usize,
    query: &str,
    editing: bool,
) -> anyhow::Result<()> {
    let (cols, rows) = terminal::size()?;
    let cols = cols as usize;
    let view = rows.saturating_sub(2) as usize;
    let start = if follow {
        lines.len().saturating_sub(view.max(1))
    } else {
        offset.min(lines.len().saturating_sub(view.max(1)))
    };
    queue!(stdout, Clear(ClearType::All), MoveTo(0, 0))?;
    for row in 0..view {
        let painted = lines
            .get(start + row)
            .map(|line| highlight(line, query, cols))
            .unwrap_or_default();
        queue!(stdout, MoveTo(0, row as u16), Print(painted))?;
    }
    let status = if editing {
        format!(" Find: {query}_   Enter search   Esc cancel   Ctrl+D back")
    } else if query.is_empty() {
        format!(" Logs · {name}   / find   wheel scroll   End follow   Ctrl+D back")
    } else {
        format!(" Find: {query}   n next   N prev   Esc clear   Ctrl+D back")
    };
    let status = clip_chars(&status, cols);
    queue!(
        stdout,
        MoveTo(0, rows.saturating_sub(1)),
        Print(format!("\x1b[30;46m{status}\x1b[0m"))
    )?;
    stdout.flush()?;
    Ok(())
}

fn highlight(line: &str, query: &str, width: usize) -> String {
    let chars: Vec<char> = line.chars().collect();
    let q: Vec<char> = query.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    let mut used = 0;
    while i < chars.len() && used < width {
        if !q.is_empty() && starts_with_ignore_ascii(&chars[i..], &q) {
            let take = q.len().min(width - used);
            out.push_str("\x1b[30;43m");
            for c in &chars[i..i + take] {
                out.push(*c);
            }
            out.push_str("\x1b[0m");
            i += take;
            used += take;
        } else {
            out.push(chars[i]);
            i += 1;
            used += 1;
        }
    }
    out
}

fn starts_with_ignore_ascii(chars: &[char], query: &[char]) -> bool {
    if query.is_empty() || chars.len() < query.len() {
        return false;
    }
    chars
        .iter()
        .zip(query)
        .all(|(c, q)| c.eq_ignore_ascii_case(q))
}

fn contains_ignore_ascii(line: &str, query: &str) -> bool {
    let chars: Vec<char> = line.chars().collect();
    let q: Vec<char> = query.chars().collect();
    if q.is_empty() || chars.len() < q.len() {
        return false;
    }
    (0..=chars.len() - q.len()).any(|i| starts_with_ignore_ascii(&chars[i..], &q))
}

fn clip_chars(text: &str, width: usize) -> String {
    text.chars().take(width).collect()
}
