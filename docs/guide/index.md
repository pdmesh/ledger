---
title: User guide
---

# Ledger user guide

Ledger turns your bank and credit card statements into one household ledger on your own
computer. You import statements as they arrive; Ledger reads them, sorts every transaction
into a category, and pairs up the ones that are two sides of the same money (a transfer
between your accounts, a card bill payment, a refund), so nothing is counted twice.

Everything stays on your computer unless you choose to use an AI service.

## Contents

1. [Install and set up](install.md): download, first launch, household and currency.
2. [Import statements](importing.md): file types, the watched folder, locked and scanned
   PDFs, checking an import, deleting one.
3. [Work with transactions](transactions.md): search and filters, totals, fixing a
   category, adding cash and other manual entries.
4. [Review reconciliation](reconciliation.md): transfers, card payments, refunds and
   duplicates, and how to confirm or reject a match.
5. [Use AI providers](ai-providers.md): local models, API keys, Claude Code and Codex,
   what gets sent, and choosing a model.
6. [Privacy, backups and your data](privacy.md): where data lives, backups, deleting.
7. [Troubleshooting](troubleshooting.md): what to do when something doesn't work.

## The ideas in one minute

- **Statements are the source.** Every transaction remembers the statement, page and row it
  came from, and the original file is archived unchanged.
- **Categories are automatic, corrections stick.** Ledger categorises with your rules,
  merchant mappings, your past corrections and, if you set one up, an AI model. When you
  change a category yourself it's pinned, and Ledger learns from it for that merchant.
- **Nothing is double counted.** Moving money between your own accounts or paying a card
  bill isn't spending. Ledger links those pairs and counts them as financial movements.
- **You review only what's uncertain.** Low-confidence categories and new matches are
  easy to find; everything else just works.

Ledger is early software (version 0.1). If something looks wrong, the
[issue tracker](https://github.com/pdmesh/ledger/issues) is the place to say so. Please
never attach a real statement; describe the layout or recreate it with made-up values.
