# Implementation status (v0.1.0)

Status of each capability against the PRD's MVP scope (section 4.1). ✅ = implemented and
tested · 🟡 = partial · ⬜ = not started.

| Capability | Status | Notes |
|---|---|---|
| Desktop application | 🟡 | The Tauri 2 shell starts and stops the sidecar and passes the per-launch token. v0.1.0 ships an unsigned Apple silicon `.dmg`; a Linux `.deb` build was verified earlier. Not yet signed or notarized. The sidecar is about 135 MB, mostly LiteLLM. |
| Local financial database | ✅ | SQLite (WAL) with Alembic migrations and a drift test. |
| Country and currency configuration | ✅ | Onboarding, presets, and base, account and transaction currencies. |
| Multiple household identities and aliases | ✅ | Ownership is inferred from statement holder blocks. |
| Bank and credit-card statement ingestion (CSV, XLSX, XLS, PDF) | ✅ | Generic header/table/line detection first, then the routed AI model for anything it can't read. Password-protected PDFs (keychain, auto-retry with remembered passwords) and scanned PDFs (read by a multimodal model) are supported. No per-bank parsers by design. |
| Canonical ledger with provenance | ✅ | Every transaction records its page, sheet, row or line and the extracted cells. |
| AI-powered classification | ✅ | Batched, validated, routed per task, with deterministic fallback. |
| Configurable taxonomy with propagation | ✅ | Rename, describe, move, merge, add and disable, with versioned propagation. |
| Merchant normalization | ✅ | Deterministic key extraction, aliases and merges; LLM canonical names are merged automatically. |
| Internal transfer detection | ✅ | |
| Credit-card reconciliation | ✅ | |
| Duplicate detection | ✅ | At document, overlapping-row and cross-format level. |
| Investment transaction classification | ✅ | Cash movements only. Portfolio valuation is out of MVP scope. |
| Incremental imports | ✅ | Idempotent. |
| Dashboard and analytics | ✅ | Overview, categories, merchants, household and period comparison. |
| Transaction search and filtering | ✅ | |
| Manual corrections and overrides | ✅ | Pinning, learning, unpin, and link confirm or reject. |
| Multiple API providers | ✅ | Through LiteLLM. Keys are stored in the OS keychain. |
| Local LLM support (P1) | ✅ | Ollama and OpenAI-compatible endpoints. |
| CLI-based model integrations (P1) | ✅ | Verified with Claude Code 2.1.318 (text and page images: a 3-page card statement read from images alone matched the text import exactly) and Codex 0.147.0 (text). Detect/Test in Settings; the model actually used is recorded. Codex's `--image` path has not been exercised against a real statement yet. |
| Folder monitoring (P1) | ✅ | Polling watcher with a seen-file index. |
| Manual transaction entry (P1) | ✅ | "Add" on Transactions; manual entries can be deleted from their detail panel. |
| Advanced multi-currency conversion (P1) | 🟡 | Rates are entered manually. There is no automatic rate source. |
| Natural language analytics (P1) | 🟡 | Answers come from aggregated facts only. There is no query planning over raw rows. |

## Resolved since v0.1

- **Scanned PDFs.** No OCR engine: pages are rendered with pypdfium2 and read by a
  multimodal model (LiteLLM vision models, Claude Code, Codex), which also returns the
  statement header. Needs an `extract` route to a model that accepts images. Up to 12
  pages are read; longer statements get a warning naming how many were skipped.
- **CLI sandboxing.** Claude Code runs with `--restricted --strict-mcp-config`: no tools
  for text prompts, and only `Read` (confined to its temporary directory, verified) for
  page images. Side effect: your Claude Code settings files aren't read, so "CLI default"
  is Claude Code's built-in default model; pick a model in Settings to control cost.
- **Password-protected PDFs.** Locked statements wait as "locked" in the Import Centre;
  the password is checked immediately, stored only in the OS keychain, and remembered
  passwords are tried on every new protected file (folder imports included).
- **Opening originals.** The backend hands files to the OS viewer (or reveals backups in
  Finder/Explorer), in the desktop app and in a browser alike. No Tauri plugin needed.
- **API token in URLs.** Removed: the token is accepted only in the `Authorization`
  header. `backend.log` also redacts any `token=` and is owner-readable only.
- **Reconciliation review.** A top-level page with a review queue, plus help tooltips
  across the app.

## Known gaps

1. **Code signing, notarization, auto-update and other platforms.** v0.1.0 ships an
   unsigned `.dmg` for Apple silicon, built locally. Signing and notarization need an
   Apple Developer ID, which only the owner can provide. Intel Mac, Windows and Linux
   builds need a CI release workflow; until then they run from source.
2. **Judge model.** The `judge` task is routable, but low-confidence second opinions are
   not invoked yet. Not needed for correctness; useful once there is more data.
3. **Evaluation harness.** Compare models against a labelled synthetic dataset (PRD 7.5).
   The router's injectable provider factory is the hook. Worth doing before tuning
   prompts or picking cheaper models.
4. **Automatic FX rates.** Rates are entered by hand; an online source would be the first
   network call the app makes on its own, so it needs an explicit opt-in design.
5. **Natural-language analytics over raw rows.** Answers come from aggregated facts only.
6. **Performance.** Benchmark with more than 100k transactions. The reconciliation
   candidate search is windowed but still in memory per run.
