# Ledger

[![CI](https://github.com/pdmesh/ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/pdmesh/ledger/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/pdmesh/ledger)](https://github.com/pdmesh/ledger/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Ledger is a free, open-source Mac app that keeps your bank and credit card statements as
one household ledger, on your own computer.

Drop in the statements you already download (PDF, CSV, XLSX or XLS), or point Ledger at a
folder. It reads each one, categorises every transaction, and pairs up transfers between
your accounts, card bill payments, refunds and duplicates so nothing is counted twice.
You review only what it isn't sure about.

**[Website](https://pdmesh.github.io/ledger/)** ·
**[Download](https://github.com/pdmesh/ledger/releases/latest)** ·
**[User guide](https://pdmesh.github.io/ledger/guide/)** ·
**[Changelog](CHANGELOG.md)**

## Features

- **Imports what banks give you.** PDF, CSV and spreadsheet statements; password-protected
  PDFs (the password stays in your keychain); scanned PDFs read by an AI model; a watched
  folder for automatic imports.
- **Categorises automatically.** Your rules, merchant mappings and corrections first, then
  an optional AI model. Every category shows how confident Ledger is and why, and your
  corrections are never overwritten.
- **Counts every dollar once.** Transfers, card payments, refunds and duplicates from
  overlapping statements are matched, with a review queue to confirm or reject matches.
- **Easy to check.** Money in and out per statement, a totals bar for any filter, and
  every transaction traced back to its statement, page and row.
- **Private.** All data stays in one folder on your Mac. No account, no server, no
  analytics.

## Install

Download `Ledger_<version>_aarch64.dmg` from the
[latest release](https://github.com/pdmesh/ledger/releases/latest) and drag Ledger to
Applications. Builds are for Macs with Apple silicon.

Ledger isn't signed with an Apple Developer ID yet. The first time you open it, macOS
blocks it: choose **Open Anyway** in **System Settings → Privacy & Security**. The
[install guide](docs/guide/install.md) covers this step by step.

Intel Macs, Windows and Linux: [build from source](#build-from-source).

## AI is optional

Ledger works without any AI: rules, merchant mappings and your corrections categorise
transactions, and anything left over is marked uncategorised. An AI provider adds
categorising for unknown merchants and reading statements with unusual layouts or scanned
pages. You can use:

- **A local model** (Ollama, LM Studio or any OpenAI-compatible server). Nothing leaves
  your computer.
- **Claude Code or Codex**, using the CLI you're already signed in to. Ledger never sees
  your login.
- **A cloud API** (Anthropic, OpenAI, Gemini and others) with your own key, kept in the
  macOS keychain.

Cloud and CLI providers are off until you allow them. They receive transaction
descriptions and amounts for categorising, and the whole statement when AI has to read
one. Details: [Use AI providers](docs/guide/ai-providers.md).

## Privacy

- Everything is stored locally: a SQLite database plus your original statements,
  unchanged.
- Only the last four digits of account and card numbers are stored. API keys and PDF
  passwords live in the macOS keychain.
- The app's local server only accepts connections from your Mac, with a key that changes
  every launch.
- Ledger makes no network calls of its own. Only AI providers you configure are contacted.
- Delete a statement and all its transactions with one action; back up everything to a
  single zip.

More in [Privacy, backups and your data](docs/guide/privacy.md).

## Build from source

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, Rust, and the
[Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for your OS.

```bash
npm install && npm --prefix frontend install && (cd backend && uv sync)
```

Run the desktop app in development (starts Vite, the Tauri window and the backend):

```bash
npm run dev
```

Or run it in a browser, with the backend and the UI in two terminals:

```bash
npm run backend
```

```bash
npm run web
```

Then open http://localhost:5173. Data goes to the OS application-data folder; set
`LEDGER_DATA_DIR` to use another one.

Build the app bundle for your platform (packages the backend with PyInstaller, then the
Tauri app):

```bash
npm run build
```

Run the tests:

```bash
npm test
```

## How it's built

A Tauri 2 shell (Rust) owns the window and starts a Python backend (FastAPI, SQLite) on
a random loopback port with a per-launch token. The UI is React and TypeScript. Imports
flow through extraction, classification and reconciliation; AI work is routed per task to
a chain of providers through LiteLLM or the CLI adapters.

| Path | What |
|---|---|
| `backend/` | Python package `ledger`: API, ingestion, classification, reconciliation, tests |
| `frontend/` | React + TypeScript + Tailwind UI |
| `src-tauri/` | Tauri 2 desktop shell |
| `scripts/build-sidecar.sh` | Packages the backend as a single executable |
| `docs/` | Website, user guide, architecture and status |

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and
[docs/STATUS.md](docs/STATUS.md) for what's done and what's next.

## Contributing

Issues and pull requests are welcome. Run `npm test` before opening a pull request.

**Never share real financial data.** Don't attach real statements, ledgers, backups or
logs to issues, and don't commit them. Tests use synthetic statements with fictional
institutions and people, generated by `backend/tests/fixtures/make_fixtures.py`; add new
cases the same way, with made-up values.

## License

[MIT](LICENSE)
