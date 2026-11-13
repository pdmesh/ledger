"""Open files with the operating system's own apps.

The backend runs on the user's machine as the user, so it can hand a file to the default
viewer (or reveal it in Finder/Explorer) directly. That works the same in the desktop app
and in a browser during development, and needs no download URL carrying the API token.
Callers pass only paths they resolved inside the data folder themselves.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class OpenError(Exception):
    pass


def open_path(path: Path, *, reveal: bool = False) -> None:
    if not path.exists():
        raise OpenError("file not found")
    try:
        if sys.platform == "darwin":
            cmd = ["open", "-R", str(path)] if reveal else ["open", str(path)]
        elif os.name == "nt":  # pragma: no cover - exercised on Windows only
            if reveal:
                cmd = ["explorer", f"/select,{path}"]
            else:
                os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
                return
        else:
            cmd = ["xdg-open", str(path.parent if reveal else path)]
        subprocess.Popen(  # noqa: S603 - fixed program, path from the data folder
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError as e:
        raise OpenError(f"could not open the file: {e}") from e
