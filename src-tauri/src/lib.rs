//! Desktop shell: owns the window and the lifecycle of the local Python backend.
//!
//! On launch it picks a free loopback port and a random per-launch API token, starts the
//! backend (a bundled sidecar in release builds, `uv run` in development) and hands both
//! to the UI through the `backend_config` command. The backend is stopped on exit.

use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{Manager, RunEvent, State};

struct Backend {
    url: String,
    token: String,
    child: Mutex<Option<Child>>,
}

#[derive(serde::Serialize)]
struct BackendConfig {
    url: String,
    token: String,
}

#[tauri::command]
fn backend_config(state: State<'_, Backend>) -> BackendConfig {
    BackendConfig {
        url: state.url.clone(),
        token: state.token.clone(),
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

fn backend_command() -> std::io::Result<Command> {
    if cfg!(debug_assertions) {
        // Development: run the backend from source with uv.
        let project = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend");
        let mut c = Command::new("uv");
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

fn spawn_backend(data_dir: PathBuf, port: u16, token: &str) -> std::io::Result<Child> {
    std::fs::create_dir_all(&data_dir)?;
    let mut cmd = backend_command()?;
    cmd.arg("--port")
        .arg(port.to_string())
        .arg("--data-dir")
        .arg(&data_dir)
        .env("LEDGER_API_TOKEN", token)
        .env("LEDGER_PARENT_PID", std::process::id().to_string());
    cmd.spawn()
}

pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let port = free_port();
            let token = random_token();
            let data_dir = app.path().app_data_dir()?;
            let child = match spawn_backend(data_dir, port, &token) {
                Ok(c) => Some(c),
                Err(e) => {
                    eprintln!("failed to start ledger backend: {e}");
                    None
                }
            };
            app.manage(Backend {
                url: format!("http://127.0.0.1:{port}"),
                token,
                child: Mutex::new(child),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_config])
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
