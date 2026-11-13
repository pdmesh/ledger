# Ledger

A local-first desktop application that turns heterogeneous bank, credit-card and investment
statements into one continuously maintained, searchable household ledger.

Drop statements in (PDF, CSV, XLSX, XLS), or point it at a folder. Ledger identifies each
document, extracts the transactions, normalizes merchants, classifies everything, reconciles
transfers, card settlements, refunds and duplicates, and produces cash-flow analytics, without
asking you to review each row.

> Capture everything. Classify intelligently. Reconcile automatically. Explore freely.

**Status:** early MVP (v0.1). See [docs/STATUS.md](docs/STATUS.md) for what is implemented
against the product requirements and what is next.

## Architecture at a glance

```
┌──────────── Tauri 2 shell (Rust) ────────────┐
│  window · picks loopback port + random token │
│  starts/stops the Python sidecar             │
│  ┌───────── React + TS UI (Vite) ─────────┐  │
│  │ Overview · Transactions · Accounts ·   │  │
│  │ Import Centre · Analytics · Settings   │  │
│  └──────────────┬─────────────────────────┘  │
└─────────────────┼────────────────────────────┘
                  │ HTTP on 127.0.0.1 + bearer token
┌─────────────────▼── Python backend (FastAPI) ──────────────────────────┐
│ ingestion ─► extraction ─► classification ─► reconciliation ─► ledger  │
│     │             │              │                  │                  │
│ archive      tabular/PDF    rules · merchants ·   transfers ·          │
│ (originals)  + LLM fallback history · LLM         settlements · refunds│
│                                  │                · duplicates         │
│                       intelligence router (task → provider chain)      │
│                       LiteLLM (API + local) · CLI adapters             │
│ persistent job queue · versioned config · analytics · SQLite (Alembic) │
└────────────────────────────────────────────────────────────────────────┘
```

Read more in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

| Path | What |
|---|---|
| `backend/` | Python package `ledger` (FastAPI app, domain model, engines, tests) |
| `frontend/` | React + TypeScript + Tailwind UI |
| `src-tauri/` | Tauri 2 desktop shell |
| `scripts/build-sidecar.sh` | Builds the backend into a single executable for bundling |
| `docs/` | Architecture, status and design notes |

## Getting started

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, Rust (for the
desktop shell), and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for
your OS.

```bash
npm install
```

```bash
(cd frontend && npm install)
```

```bash
(cd backend && uv sync)
```

**Run as a desktop app (development).** Starts Vite and the Tauri window; the shell runs
the backend from source with `uv`:

```bash
npm run dev
```

**Run in a browser (development).** Two terminals:

```bash
npm run backend
```

```bash
npm run web
```

Then open http://localhost:5173. Data goes to the OS application-data folder; set
`LEDGER_DATA_DIR` to use another location.

**Build a distributable app.** Builds the Python sidecar with PyInstaller, then bundles it:

```bash
npm run build
```

**Tests.**

```bash
npm test
```

## Intelligence providers

Nothing is enabled by default. Without a provider, Ledger is fully deterministic: shipped
and user rules, merchant mappings and your corrections classify transactions, and anything
left over is marked uncategorized with low confidence.

In **Settings → Intelligence providers** you can add:

- **Local models**: Ollama, MLX servers or any OpenAI-compatible endpoint (via LiteLLM).
  Always allowed, and no data leaves the device.
- **API providers**: Anthropic, OpenAI, Gemini or any LiteLLM-supported provider, with
  your own keys stored in the OS keychain.
- **CLI agents**: your own installed and logged-in Claude Code or Codex CLI, invoked in
  non-interactive mode in an empty temporary directory. Ledger never bundles these
  binaries or reads their credentials.

Cloud and CLI providers are only used after you turn on *Allow cloud and CLI providers*.
Household names are pseudonymized in categorisation and matching prompts unless you opt
in. When a statement has to be read by AI (a layout the generic parser can't handle, or a
scanned PDF), the whole statement goes to the routed `extract` provider as text or page
images, unredacted; route `extract` to a local model to keep that on the device. Claude
Code runs with `--restricted --strict-mcp-config`, no tools for text and only `Read`
(confined to its temporary directory) for page images. Each task
(classify, merchant, extract, identity, reconcile, judge, query) can be routed to its own
provider chain with fallbacks, and every call is recorded with model, tokens, cost and
latency, but never the prompt contents.

## Privacy

- Everything is stored locally: SQLite database plus an archive of the original files,
  which are never modified.
- Only the last four digits of account and card numbers are persisted.
- The backend listens on `127.0.0.1` only and requires a per-launch random token, sent only
  in the `Authorization` header (never in URLs). Originals open in the OS's own viewer.
- You can delete any imported document together with all its transactions, and you can
  create and restore full backups.

### Keeping the repository free of personal data

This repository is meant to be publishable. Test fixtures are **synthetic**: fictional
institutions (Northwind, Contoso, Fabrikam) and people ("Alex Sample", "Sam Sample"),
generated by `backend/tests/fixtures/make_fixtures.py`. `.gitignore` excludes databases,
backups, `statements/` and `.env` files. Never commit real statements. To add a regression
case for a real bank's format, recreate its layout with made-up values.

## License

To be decided before publication.
