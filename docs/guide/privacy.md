---
title: Privacy, backups and your data
---

# Privacy, backups and your data

[← User guide](index.md)

## Where your data lives

Everything is in one folder on your Mac:

```
~/Library/Application Support/dev.personal-ledger.app/
  ledger.sqlite3   the ledger database
  archive/         your original statements, stored unchanged
  backups/         backups you create
  backend.log      diagnostic log (readable only by you)
```

- Only the last four digits of account and card numbers are stored.
- API keys and PDF passwords are kept in the macOS keychain, never in the database.
- The ledger runs a small local server for its own window. It only accepts connections
  from your Mac, and only with a key that changes every time the app starts.

## What leaves your computer

Nothing, unless you turn on a cloud or CLI provider. Then transaction descriptions and
amounts are sent for categorising, and whole statements when AI has to read one. See
[Use AI providers](ai-providers.md#allowing-cloud-and-cli-providers) for the details, and
route work to a local model to keep it on your computer. Ledger doesn't send analytics or
check for updates.

## Backups

**Settings → Privacy & data → Create backup** writes one zip with the database and every
archived statement to the `backups` folder. **Show in folder** reveals it in Finder so
you can copy it somewhere safe. Backups contain your full financial history; keep them
somewhere private.

**Restore this backup…** replaces the current ledger with the backup the next time the
app starts.

## Deleting data

- Delete one statement and its transactions from the **Import Centre**.
- Delete a transaction you entered by hand from its details panel.
- To remove everything, quit Ledger and delete the folder above.

## Configuration history

Every change to categories, merchants, rules, people or AI settings is versioned under
**Settings → Privacy & data → Configuration history**. A change marked **Applied to
existing transactions** was re-run over transactions you already had (your pinned values
are left alone). **AI re-classification** means the affected transactions are being
re-categorised in the background, including by your AI providers.
