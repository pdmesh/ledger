"""Entry point for the local backend (run directly in dev, or as the Tauri sidecar)."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Ledger local backend")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LEDGER_PORT", "8765")))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    import uvicorn

    from ledger.app import create_app
    from ledger.settings import RuntimeSettings

    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s %(message)s")
    rt = RuntimeSettings(port=args.port)
    if args.data_dir:
        rt.data_dir = args.data_dir.expanduser()
    app = create_app(rt)
    # Loopback only: the ledger is never exposed on the network.
    uvicorn.run(app, host="127.0.0.1", port=rt.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
