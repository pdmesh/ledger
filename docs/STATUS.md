# Implementation status (v0.1)

Status of each capability against the PRD's MVP scope (section 4.1). ✅ = implemented and
tested · 🟡 = partial · ⬜ = not started.

| Capability | Status | Notes |
|---|---|---|
| Desktop application | 🟡 | The Tauri 2 shell starts and stops the sidecar and passes the per-launch token, verified with a Linux `.deb` release build. The macOS `.app`/`.dmg` targets are configured but have not been built or signed. The sidecar is about 135 MB, mostly LiteLLM. |
| Local financial database | ✅ | SQLite (WAL) with Alembic migrations and a drift test. |
| Country and currency configuration | ✅ | Onboarding, presets, and base, account and transaction currencies. |
| Multiple household identities and aliases | ✅ | Ownership is inferred from statement holder blocks. |
| Bank and credit-card statement ingestion (CSV, XLSX, XLS, PDF) | ✅ | Header detection, wrapped descriptions, sign resolution from running balance or Cr/Dr markers, per-document card polarity. |
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
| CLI-based model integrations (P1) | 🟡 | Claude Code and Codex adapters exist. CLI flags are configurable but have not been verified against every CLI release. |
| Folder monitoring (P1) | ✅ | Polling watcher with a seen-file index. |
| Manual transaction entry (P1) | 🟡 | The API exists; there is no UI form yet. |
| Advanced multi-currency conversion (P1) | 🟡 | Rates are entered manually. There is no automatic rate source. |
| Natural language analytics (P1) | 🟡 | Answers come from aggregated facts only. There is no query planning over raw rows. |

## Known gaps and next steps

1. **OCR for scanned PDFs.** Wire Tesseract (or a vision model through the `extract`
   task).
2. **Password-protected PDFs.** The plumbing exists in `read_pdf`, but there is no prompt or
   keychain flow in the UI yet.
3. **Real-format corpus.** Recreate the layouts of common banks with synthetic values,
   measure extraction accuracy, and add per-institution adapters where generic detection
   falls short.
4. **Evaluation harness.** Compare models against a labelled synthetic dataset, as described
   in PRD section 7.5. The router's injectable provider factory is the hook for this.
5. **Judge model.** The `judge` task is routable, but low-confidence second opinions are not
   invoked yet.
6. **Opening links from the desktop shell.** Add `tauri-plugin-opener`, so that "open
   original document" uses the OS viewer.
7. **Code signing and auto-update** for macOS distribution.
8. **Performance.** Benchmark with more than 100k transactions. The reconciliation
   candidate search is windowed but still in-memory per run.
