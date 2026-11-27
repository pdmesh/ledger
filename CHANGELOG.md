# Changelog

## 0.1.0 (2026-11-27)

First public release. A macOS app (Apple silicon, unsigned) that keeps your bank and
credit card statements as one categorised, reconciled household ledger, on your computer.

### Importing
- PDF, CSV, XLSX and XLS statements, by drag and drop, file picker or a watched folder.
- Institution, account, owner and statement period detected automatically; accounts
  created on first sight; re-imports and overlapping statements de-duplicated.
- Statements with unusual layouts are read by your AI provider; scanned PDFs are read by
  a multimodal model (no OCR engine needed).
- Password-protected PDFs: unlock once, password kept in the macOS keychain and tried on
  future protected statements.
- Money in / money out per statement for checking an import against the bill; deleting a
  statement removes all its transactions.

### Ledger
- Automatic categories from rules, merchant mappings, your corrections and AI, with
  confidence and an explanation for each; corrections are pinned and learned.
- Reconciliation of transfers, card bill payments, refunds and duplicates, with a review
  queue to confirm or reject matches.
- Transactions search and filters, a totals bar for any filter, a per-statement breakdown,
  and manual entries for cash.
- Overview and analytics by category, merchant, household member and period.

### AI providers (optional)
- Local models (Ollama and OpenAI-compatible servers), cloud APIs with your own key, and
  Claude Code or Codex using your existing login.
- Per-task routing with fallbacks; every call listed with model, latency and cost.
- Claude Code runs restricted: no tools for text, read-only access to its own temporary
  folder for page images.

### Privacy
- All data in one local folder; keys and PDF passwords in the keychain; only the last four
  digits of account numbers stored.
- The local server accepts its per-launch token only in a request header; the app makes
  no network calls of its own.

### Known limitations
- Not signed or notarized: macOS asks you to allow it on first launch.
- Apple silicon only as a download; other platforms run from source.
- See [docs/STATUS.md](docs/STATUS.md) for what's next.
