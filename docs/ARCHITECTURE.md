# Architecture

## Processes

| Process | Role |
|---|---|
| Tauri shell (`src-tauri/`) | Owns the window. On launch it picks a free loopback port and a random 256-bit token, starts the backend and exposes both to the UI via the `backend_config` command. It kills the backend on exit. |
| Backend (`backend/`) | FastAPI app on `127.0.0.1:<port>`. In release builds it is a PyInstaller one-file sidecar; in development it runs as `uv run ledger-server`. A single background worker thread drains the persistent job queue. |
| UI (`frontend/`) | React SPA. Calls `/api/*` with `Authorization: Bearer <token>`. |

## Backend modules

| Module | Responsibility |
|---|---|
| `models.py` | SQLAlchemy model: configuration (identities, institutions, accounts, taxonomy, merchants, rules, settings, FX rates) and ledger (documents, transactions, overrides, classification history, reconciliation links, AI executions, jobs). |
| `db.py` | Engine/session; `Money` (exact decimals stored as scaled integers) and `JSONText` types. |
| `migrate.py`, `migrations/` | Alembic migrations, applied automatically at startup. `python -m ledger.migrate "msg"` autogenerates a new revision. |
| `config.py` | Settings access, per-scope and global **configuration versions**, change log and first-run seeding. |
| `defaults.py` | Default taxonomy, system rules, settings, country presets and institution hints. |
| `ingestion/` | `register_file` (hash, archive, idempotency), `extract` (format dispatch), `tabular` (header detection for CSV/XLSX/XLS/PDF tables), `pdf` (tables, then a line-pattern fallback), `metadata` (institution, document type, last-4 digits, holder, period, balances), `service` (account resolution, ownership, fingerprints, insertion, classification, reconciliation), `folder` (watched folder). |
| `classification/` | `merchants` (alias index, key extraction, merges), `rules` (compiled deterministic rules), `engine` (precedence chain, history learning, LLM batching, recurrence). |
| `identity.py` | Alias matching and **account-level** ownership inference. |
| `reconciliation/engine.py` | Duplicate, card-settlement, internal-transfer and refund matching with evidence, confidence, ambiguity handling and optional LLM adjudication. |
| `intelligence/` | `providers` (LiteLLM, CLI adapters, keychain), `router` (task routing, fallbacks, privacy and execution records), `context` (Financial Context Package), `tasks` (prompts and strict validators). |
| `propagation.py` | Turns configuration changes into the minimum necessary recomputation. |
| `jobs.py` | Persistent job queue and worker; `running` jobs are re-queued on start. |
| `analytics/service.py` | Role-based metrics, time series, category/merchant breakdowns and household views. |
| `api/` | HTTP routers and explicit serializers (the frontend contract). |

## Key design decisions

### Signed amounts and roles

- Every transaction stores a **signed** amount from the account's point of view (inflows are
  positive), along with the original currency. `base_amount` is derived and recomputable.
- The taxonomy is a user-editable tree. Only the five root **roles** are fixed (income,
  expense, investment, transfer, adjustment), and each category inherits its root's role.
  Analytics are computed from roles, so renaming, moving or merging categories never breaks
  a metric.
- The metrics are defined as follows:
  - Consumption is outflows with role `expense` minus refunds (role `adjustment`).
  - Income is inflows with role `income`.
  - Financial movements (role `transfer`: internal transfers, card settlements, cash) are
    excluded from both, so nothing is counted twice.

### Credit cards

Card purchases are expenses on the card account. The bank's bill payment and the card's
"payment received" are both classified as `card-settlement` (role transfer) and linked.
The bank-side payment is recognized by a rule even when the card statement hasn't been
imported yet.

### Provenance and immutability

- Originals are archived byte-for-byte under `archive/<sha[:2]>/<sha>.<ext>`.
- Transactions keep `description_raw`, `raw` (the extracted cells), `source_ref`
  (page/sheet/row/line) and how each sign was determined (`sign_basis`).
- Classification never overwrites source fields. Every decision is appended to
  `classification_records`, along with its method, confidence, evidence, configuration
  version and AI execution id.
- User corrections are stored in `transaction_overrides` and pin the field
  (`pinned_fields`). Automated processing never touches a pinned field.

### Classification precedence

1. User pins.
2. Active reconciliation links.
3. User merchant mappings.
4. Rules (user/learned before system).
5. History: the majority of your corrections for the merchant, or an earlier AI decision
   for it.
6. LLM, batched and only for what's left.
7. Fallback by direction.

Learning from corrections works like this. A correction made with *apply to similar*
becomes a user merchant mapping, and it propagates to the history and to future imports.

### Duplicate detection

- **Documents.** A document whose SHA-256 is already known is a duplicate.
- **Rows.** Each row's fingerprint is `account|date|amount|normalized description|reference|occurrence#`.
  The occurrence index counts identical rows within one document. Two genuinely identical
  coffees on the same day stay distinct, while the *k*-th identical row of an overlapping
  statement matches the *k*-th row already in the ledger.
- **Within one document.** An identical row with an identical running balance is a
  duplicate.
- **Across formats.** Rows from other documents on the same account, with the same amount,
  a date within one day and a similar description or the same reference, are linked. They
  are flagged as duplicates when confidence ≥ the threshold, which defaults to 0.85.
- Flagged duplicates stay in the ledger with `duplicate_of_id` set and are excluded from
  analytics. Rejecting a duplicate link restores the row.

### Transfer and settlement matching

Candidates must have:

- the same currency and absolute amount,
- opposite directions,
- different accounts,
- dates within the configured window.

The score starts from date proximity. Evidence raises it:

- rail or transfer keywords,
- the counterpart's last four digits in the description,
- the same reference,
- the card institution's name.

A side that you pinned, or that a strong rule or mapping put in income, expense or
investment, needs explicit transfer cues on both sides. This stops a salary from being
paired with an unrelated rent payment that happens to have the same amount.

Ties within 0.05 go to the `reconcile` model if one is routed. Otherwise they are broken
deterministically, with reduced confidence and the alternatives recorded. Rejected pairs
are remembered and never re-linked.

### Configuration versioning and propagation

Each change bumps its scope's version and the global version, and is logged with its
propagation class:

| Change | Propagation |
|---|---|
| Category rename | none (rows reference the id) |
| Move/merge category, merchant mapping or alias, rule, account type or owners, identity alias | deterministic re-run (no model calls; an existing classification is kept unless a deterministic layer now matches or its rule was removed) |
| Category description changed, category added or disabled | `ai`: affected AI, fallback and history rows are re-run through the full chain in the background |

Jobs are coalesced with dedupe keys, so a burst of edits results in one recomputation.

## Answers to the PRD's open technical questions

1. **Backend process model.** A sidecar. PyInstaller builds a one-file executable that
   Tauri bundles through `externalBin`, and in development the shell runs `uv run`. The
   shell owns the lifecycle, and communication goes over loopback HTTP with a per-launch
   token.
2. **LiteLLM embedding.** Embedded as a library inside the backend, with no separate proxy
   service. That means one fewer process and no extra port, and the keys stay in the OS
   keychain.
3. **Local inference first.** Ollama (`ollama_chat/...`) and any OpenAI-compatible server
   (`openai/...` plus `api_base`), which covers MLX-LM, LM Studio, llama.cpp and vLLM.
   Both go through LiteLLM and are flagged `local` for privacy routing.
4. **Parsing libraries.**
   - pdfplumber (MIT), for text plus tables, with a regex line parser as the fallback.
   - openpyxl (MIT) for XLSX and xlrd (BSD) for legacy XLS.
   - The standard-library `csv` module, with dialect sniffing.
   - PyMuPDF is AGPL, so it was avoided to keep licensing open.
   - OCR (Tesseract) is pluggable but not yet wired. Scanned PDFs fail with a clear message,
     or go through the LLM extraction fallback if you route one.
5. **CLI structured output.** Each adapter declares its arguments and output convention:
   Claude Code's JSON envelope and Codex's last-message file. The prompt is sent on stdin
   and asks for JSON only. The reply then goes through the same tolerant JSON extraction
   and strict per-task validation as API models. The CLIs run in an empty temporary
   directory with a timeout.
6. **FX rates.** A user-maintained historical `fx_rates` table, with the closest earlier
   rate within 10 days and inverse lookup. Base amounts are recomputed when rates or the
   base currency change. Automatic rate sources can feed the same table later.
7. **Joint accounts and inter-member transfers.**
   - Ownership lives on the account (`account_owners`), and an account with more than one
     owner is joint.
   - The household view counts each transaction once.
   - Individual views include the person's own and joint accounts, plus any transactions
     explicitly attributed to them.
   - Transfers between members are internal transfers, and their evidence records
     `between_household_members`.
8. **Classification versioning and bulk reclassification.**
   - Each row stores the configuration version it was classified under, and history is
     append-only.
   - Reclassification is driven by filters (category, merchant, method), runs in the
     background and is deterministic unless meaning changed.
   - LLM calls are batched (40 per call by default), and merchant-level AI decisions are
     cached on the merchant, so similar rows don't trigger new calls.
