#!/usr/bin/env bash
# Build the Python backend into a single self-contained executable and place it where
# Tauri expects sidecars: src-tauri/binaries/ledger-backend-<target-triple>.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRIPLE="$(rustc -vV | sed -n 's/^host: //p')"
cd "$ROOT/backend"
uv sync --frozen
uv run --with pyinstaller pyinstaller \
  --noconfirm --clean --onefile \
  --name ledger-backend \
  --collect-submodules ledger \
  --collect-data litellm \
  --collect-data ledger \
  --copy-metadata litellm \
  --add-data "src/ledger/migrations:ledger/migrations" \
  src/ledger/server.py
mkdir -p "$ROOT/src-tauri/binaries"
EXT=""; [[ "$TRIPLE" == *windows* ]] && EXT=".exe"
cp "dist/ledger-backend$EXT" "$ROOT/src-tauri/binaries/ledger-backend-$TRIPLE$EXT"
echo "sidecar: src-tauri/binaries/ledger-backend-$TRIPLE$EXT"
