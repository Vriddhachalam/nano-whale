mod app;
mod chart;
mod config;
mod docker;
mod model;
mod stats_parse;
mod theme;
mod term_logs;
mod textutil;
mod ui;

use std::io::stdout;
use std::panic;
use std::time::{Duration, Instant};

use anyhow::Context;
use clap::Parser;
use crossterm::event::{
    self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEvent, KeyEventKind,
    KeyModifiers,
};
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::ExecutableCommand;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use tokio::sync::mpsc;

use app::App;
use config::Config;
use docker::{connect, spawn_workers};

const VERSION: &str = "2.0.0";

#[derive(Parser, Debug)]
#[command(name = "nano-whale", version = VERSION, about = "Lightweight Docker TUI")]
struct Cli {}

fn drain_terminal_events(
    terminal: &mut Terminal<ratatui::backend::CrosstermBackend<std::io::Stdout>>,
    app: &mut App,
    tx: &tokio::sync::mpsc::UnboundedSender<crate::model::DockerEvent>,
) -> anyhow::Result<()> {
    while event::poll(Duration::from_millis(0))? {
        match event::read()? {
            Event::Resize(_, _) => {
                terminal.autoresize()?;
                terminal.clear()?;
                app.state.mark_dirty();
            }
            Event::Key(key) if key.kind == KeyEventKind::Press => {
                app.handle_key(key, tx);
                app.state.mark_dirty();
            }
            Event::Mouse(mouse) => app.handle_mouse(mouse.kind, mouse.column, mouse.row),
            _ => {}
        }
    }
    Ok(())
}

/// Leave the TUI, attach an interactive shell, then restore the screen.
fn open_container_terminal(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    name: &str,
) -> anyhow::Result<()> {
    suspend_tui(terminal, || {
        println!("\nTerminal · {name}\nType exit or Ctrl+D to return to nano-whale.\n");
        std::process::Command::new("docker")
            .env("DOCKER_CLI_HINTS", "false")
            .args([
                "exec",
                "-it",
                name,
                "sh",
                "-c",
                "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi",
            ])
            .status()
            .map(|_| ())
            .context("docker exec")
    })
}

fn open_container_logs(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    name: &str,
    tail: usize,
) -> anyhow::Result<()> {
    suspend_tui(terminal, || term_logs::run(name, tail))
}

/// `docker logs` ignores EOF. Ctrl+D is recognized here and in the log viewer.
pub(crate) fn is_ctrl_d(key: KeyEvent) -> bool {
    key.modifiers.contains(KeyModifiers::CONTROL)
        && matches!(key.code, KeyCode::Char('d') | KeyCode::Char('D'))
}

fn suspend_tui(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    run: impl FnOnce() -> anyhow::Result<()>,
) -> anyhow::Result<()> {
    let _ = stdout().execute(DisableMouseCapture);
    disable_raw_mode().ok();
    let _ = stdout().execute(LeaveAlternateScreen);
    let _ = terminal.show_cursor();
    let result = run();
    enable_raw_mode().context("restore raw mode")?;
    stdout()
        .execute(EnterAlternateScreen)
        .context("restore screen")?;
    let _ = stdout().execute(EnableMouseCapture);
    terminal.clear()?;
    result
}

fn install_panic_hook() {
    let hook = panic::take_hook();
    panic::set_hook(Box::new(move |info| {
        let _ = disable_raw_mode();
        let _ = stdout().execute(DisableMouseCapture);
        let _ = stdout().execute(LeaveAlternateScreen);
        hook(info);
    }));
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let _cli = Cli::parse();

    install_panic_hook();

    let docker = connect()?;
    let config = Config::default();
    let hostname = std::env::var("HOSTNAME")
        .or_else(|_| std::env::var("COMPUTERNAME"))
        .unwrap_or_else(|_| "localhost".into());

    let (tx, mut rx) = mpsc::unbounded_channel();
    let mut app = App::new(docker.clone(), config.clone(), hostname);
    spawn_workers(docker.clone(), config.clone(), tx.clone(), app.stats_target.clone());
    app.sync_stats_target();
    app.bootstrap_streams(&tx);

    enable_raw_mode().context("enable raw mode")?;
    stdout()
        .execute(EnterAlternateScreen)
        .context("enter alternate screen")?;
    let mut terminal = Terminal::new(CrosstermBackend::new(stdout()))?;
    let _ = stdout().execute(EnableMouseCapture);
    terminal.clear()?;

    let mut last_draw = Instant::now();
    let min_frame = config.tick_rate;

    while !app.state.quit {
        app.drain_events(&mut rx, &tx);

        if app.state.notify.as_ref().is_some_and(|n| Instant::now() >= n.until) {
            app.state.notify = None;
            app.state.mark_dirty();
        }

        let should_draw = app.state.dirty && last_draw.elapsed() >= min_frame;
        if should_draw {
            terminal.draw(|f| ui::draw(f, &mut app.state, &app.config))?;
            app.state.dirty = false;
            last_draw = Instant::now();
        }

        let wait = if app.state.dirty {
            min_frame.saturating_sub(last_draw.elapsed())
        } else {
            config.idle_tick_rate
        };

        if event::poll(wait)? {
            drain_terminal_events(&mut terminal, &mut app, &tx)?;
        }

        if let Some(name) = app.state.shell_container.take() {
            if let Err(err) = open_container_terminal(&mut terminal, &name) {
                app.state.set_notify(format!("Terminal: {err}"), true);
            }
            app.state.mark_dirty();
        }
        if let Some(name) = app.state.logs_terminal.take() {
            let tail = app.config.logs_tail;
            if let Err(err) = open_container_logs(&mut terminal, &name, tail) {
                app.state.set_notify(format!("Logs: {err}"), true);
            }
            app.state.mark_dirty();
        }
    }

    if let Some(task) = app.log_task.take() {
        task.abort();
    }

    let _ = stdout().execute(DisableMouseCapture);
    disable_raw_mode()?;
    stdout().execute(LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    Ok(())
}
