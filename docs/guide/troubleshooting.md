---
title: Troubleshooting
---

# Troubleshooting

[← User guide](index.md)

## "Cannot reach the local backend"

Ledger's window talks to a small local server that starts with the app. If it can't
start, the error screen shows the last lines of its log and the log file's location
(`backend.log` in the data folder). Choose **Try again** first; the first start after
installing or updating can take a minute. If it keeps failing, open an
[issue](https://github.com/pdmesh/ledger/issues) with the log lines (check they contain
nothing private).

## A statement failed

Click it in the Import Centre to see why.

- **No transaction table found / No transactions were extracted.** The layout wasn't
  recognised. Set up an [AI provider](ai-providers.md) and route the **extract** task to
  it, then choose **Re-process**.
- **Scanned image / needs an AI provider that can read images.** Route **extract** to a
  provider that accepts images: Claude Code, Codex, or a vision-capable API or local
  model.
- **AI extraction failed.** The model returned an error or something unusable. Check
  **Settings → Intelligence providers → Recent model calls** for the error, and use
  **Test** on the provider.

## A statement says "locked"

It's password-protected. Choose **Enter password**. If the password is rejected, check it
with your bank; some banks use a different password for older statements.

## Claude Code or Codex isn't found

Choose **Detect** on the provider. If it says *Not found*, check the CLI works in
Terminal (`claude --version` or `codex --version`). If it's installed somewhere unusual,
put its full path in **Executable**. Ledger looks in your shell's PATH and the usual
install folders.

**Test** can take up to a minute for CLI providers. If it fails with a sign-in error,
sign in to the CLI again from Terminal.

## Numbers don't add up

- Card statements: **Money in** is usually last month's bill payment and refunds, so
  compare **Money out** with the purchases on the bill.
- Check **Reconciliation → Needs review**: a wrong match moves a transaction out of
  spending. Reject it to put it back.
- Filter Transactions by **Duplicates** to see what's hidden as a duplicate.
- Accounts in another currency need exchange rates under **Settings → General**;
  transactions without a rate aren't converted.

## A category keeps coming back wrong

Correct it once on a transaction (that pins it and teaches the merchant), or add a rule
under **Settings → Classification rules**.
