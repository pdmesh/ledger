"""Entry point for the local backend (run directly in dev, or as the Tauri sidecar)."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path


def _watch_parent(pid: int) -> None:
    """Exit if the desktop shell that started us disappears (e.g. it was force-killed)."""
    import threading
    import time

    def loop() -> None:
        while True:
            time.sleep(2)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                os._exit(0)
            except (PermissionError, OSError):
                continue

    if os.name == "posix":
        threading.Thread(target=loop, name="parent-watchdog", daemon=True).start()


def _augment_path() -> None:
    """Give the backend the user's shell PATH.

    macOS apps started from Finder/Dock inherit a minimal PATH (/usr/bin:/bin:...), so
    user-installed CLIs such as ``claude`` (~/.local/bin) or ``codex`` (Homebrew/npm) are
    invisible to ``shutil.which``. Ask the login shell for its PATH and add common install
    locations as a fallback.
    """
    import subprocess

    current = os.environ.get("PATH", "").split(os.pathsep)
    extra: list[str] = []
    shell = os.environ.get("SHELL") or "/bin/zsh"
    if os.name == "posix":
        try:
            out = subprocess.run(
                [shell, "-ilc", 'printf "__LEDGER_PATH__%s" "$PATH"'],
                capture_output=True,
                text=True,
                timeout=10,
                stdin=subprocess.DEVNULL,
            )
            marker = out.stdout.rfind("__LEDGER_PATH__")
            if marker >= 0:
                extra += out.stdout[marker + len("__LEDGER_PATH__") :].strip().split(os.pathsep)
        except Exception:
            pass
    home = Path.home()
    extra += [
        str(home / ".local/bin"),
        str(home / ".claude/local"),
        str(home / ".npm-global/bin"),
        str(home / ".bun/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    merged: list[str] = []
    for p in current + extra:
        if p and p not in merged:
            merged.append(p)
    os.environ["PATH"] = os.pathsep.join(merged)


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Ledger local backend")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LEDGER_PORT", "8765")))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()
    _augment_path()

    import uvicorn

    from ledger.app import create_app
    from ledger.settings import RuntimeSettings

    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s %(message)s")
    rt = RuntimeSettings(port=args.port)
    if args.data_dir:
        rt.data_dir = args.data_dir.expanduser()
    parent = os.environ.get("LEDGER_PARENT_PID")
    if parent and parent.isdigit():
        _watch_parent(int(parent))
    app = create_app(rt)
    # Loopback only: the ledger is never exposed on the network.
    uvicorn.run(app, host="127.0.0.1", port=rt.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
