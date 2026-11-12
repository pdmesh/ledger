//! Desktop shell: owns the window and the lifecycle of the local Python backend.
//!
//! On launch it picks a free loopback port and a random per-launch API token, starts the
//! backend (a bundled sidecar in release builds, `uv run` in development) and hands both
//! to the UI through the `backend_config` command. Backend output is kept in memory (and
//! appended to `backend.log` in the data folder) so the UI can explain start-up failures
//! via `backend_status`. The backend is stopped on exit.

use std::collections::VecDeque;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use tauri::{Manager, RunEvent, State};

const LOG_LINES: usize = 200;

struct Backend {
    url: String,
    token: String,
    child: Mutex<Option<Child>>,
    spawn_error: Option<String>,
    log: Arc<Mutex<VecDeque<String>>>,
    log_file: PathBuf,
}

#[derive(serde::Serialize)]
struct BackendConfig {
    url: String,
    token: String,
}

#[derive(serde::Serialize)]
struct BackendStatus {
    url: String,
    running: bool,
    exit_code: Option<i32>,
    spawn_error: Option<String>,
    log_tail: Vec<String>,
    log_file: String,
}

#[tauri::command]
fn backend_config(state: State<'_, Backend>) -> BackendConfig {
    BackendConfig {
        url: state.url.clone(),
        token: state.token.clone(),
    }
}

#[tauri::command]
fn backend_status(state: State<'_, Backend>) -> BackendStatus {
    let (running, exit_code) = match state.child.lock().unwrap().as_mut() {
        Some(child) => match child.try_wait() {
            Ok(None) => (true, None),
            Ok(Some(status)) => (false, status.code()),
            Err(_) => (false, None),
        },
        None => (false, None),
    };
    let log = state.log.lock().unwrap();
    BackendStatus {
        url: state.url.clone(),
        running,
        exit_code,
        spawn_error: state.spawn_error.clone(),
        log_tail: log.iter().rev().take(40).rev().cloned().collect(),
        log_file: state.log_file.display().to_string(),
    }
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

fn random_token() -> String {
    let mut buf = [0u8; 32];
    getrandom::getrandom(&mut buf).expect("OS random source unavailable");
    buf.iter().map(|b| format!("{b:02x}")).collect()
}

/// Find `uv` even when the app was started without the user's shell PATH
/// (e.g. from Finder or an IDE on macOS).
fn find_uv() -> PathBuf {
    let name = if cfg!(windows) { "uv.exe" } else { "uv" };
    let mut dirs: Vec<PathBuf> = std::env::var_os("PATH")
        .map(|p| std::env::split_paths(&p).collect())
        .unwrap_or_default();
    if let Some(home) = std::env::var_os("HOME").map(PathBuf::from) {
        dirs.push(home.join(".local/bin"));
        dirs.push(home.join(".cargo/bin"));
    }
    dirs.push(PathBuf::from("/opt/homebrew/bin"));
    dirs.push(PathBuf::from("/usr/local/bin"));
    dirs.into_iter()
        .map(|d| d.join(name))
        .find(|p| p.is_file())
        .unwrap_or_else(|| PathBuf::from(name))
}

fn backend_command() -> std::io::Result<Command> {
    if cfg!(debug_assertions) {
        // Development: run the backend from source with uv.
        let project = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend");
        let mut c = Command::new(find_uv());
        c.arg("run").arg("--project").arg(project).arg("ledger-server");
        Ok(c)
    } else {
        // Release: the PyInstaller-built sidecar is bundled next to the app executable.
        let exe = std::env::current_exe()?;
        let dir = exe.parent().expect("executable has a parent directory");
        let name = if cfg!(windows) { "ledger-backend.exe" } else { "ledger-backend" };
        Ok(Command::new(dir.join(name)))
    }
}

/// Forward a child stream to stderr, the in-memory tail and the log file.
fn pump<R: Read + Send + 'static>(stream: R, log: Arc<Mutex<VecDeque<String>>>, file: PathBuf) {
    std::thread::spawn(move || {
        let mut out = OpenOptions::new().create(true).append(true).open(&file).ok();
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            eprintln!("[backend] {line}");
            if let Some(f) = out.as_mut() {
                let _ = writeln!(f, "{line}");
            }
            let mut buf = log.lock().unwrap();
            if buf.len() >= LOG_LINES {
                buf.pop_front();
            }
            buf.push_back(line);
        }
    });
}

fn spawn_backend(
    data_dir: &Path,
    port: u16,
    token: &str,
    log: &Arc<Mutex<VecDeque<String>>>,
    log_file: &Path,
) -> std::io::Result<Child> {
    std::fs::create_dir_all(data_dir)?;
    let mut cmd = backend_command()?;
    cmd.arg("--port")
        .arg(port.to_string())
        .arg("--data-dir")
        .arg(data_dir)
        .env("LEDGER_API_TOKEN", token)
        .env("LEDGER_PARENT_PID", std::process::id().to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    if let Some(s) = child.stdout.take() {
        pump(s, log.clone(), log_file.to_path_buf());
    }
    if let Some(s) = child.stderr.take() {
        pump(s, log.clone(), log_file.to_path_buf());
    }
    Ok(child)
}

pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let port = free_port();
            let token = random_token();
            let data_dir = app.path().app_data_dir()?;
            let log_file = data_dir.join("backend.log");
            let log = Arc::new(Mutex::new(VecDeque::with_capacity(LOG_LINES)));
            let (child, spawn_error) = match spawn_backend(&data_dir, port, &token, &log, &log_file) {
                Ok(c) => (Some(c), None),
                Err(e) => {
                    let msg = format!("could not start the backend: {e}");
                    eprintln!("{msg}");
                    (None, Some(msg))
                }
            };
            app.manage(Backend {
                url: format!("http://127.0.0.1:{port}"),
                token,
                child: Mutex::new(child),
                spawn_error,
                log,
                log_file,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_config, backend_status])
        .build(tauri::generate_context!())
        .expect("error while building the application");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(state) = handle.try_state::<Backend>() {
                if let Some(mut child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
