---
title: Review reconciliation
---

# Review reconciliation

[← User guide](index.md)

Some money shows up twice across your statements because it's one movement seen from two
sides. Ledger pairs these up so they aren't counted as spending or income twice:

| Kind | Example | Effect |
|---|---|---|
| Transfer | Savings → current account | Both sides count as a financial movement, not income or spending. |
| Card payment | Bank account pays the credit card bill | The bill payment isn't counted on top of the card purchases. |
| Refund | A returned order | The refund reduces what the purchase counts as spending. |
| Duplicate | The same row in two overlapping statements | The copy is hidden from totals. |

Nothing is ever deleted by reconciliation; it only relates transactions to each other.

## Reviewing matches

Matches take effect as soon as they're found. **Reconciliation** in the sidebar shows a
count of matches you haven't reviewed yet.

The **Needs review** tab lists them, least certain first. Each card shows both
transactions in plain words (for example *Bank payment* and *Card*), the match confidence
and how it was found. Click either side to open that transaction.

- **Confirm** keeps the match. Later re-runs never undo it.
- **Reject** separates the pair: both transactions are categorised on their own again,
  and Ledger never pairs them again.

The **Confirmed**, **Rejected** and **All** tabs show your earlier decisions, and you can
change your mind at any time.

## Matching rules

**Settings → Reconciliation rules** sets how far apart in time the two sides can be:

- **Transfers**: days between leaving one account and arriving in the other.
- **Card payments**: days after a card statement that a bank payment can still settle it.
- **Refunds**: how long after a purchase a refund can be matched to it.
- **Duplicate threshold**: how confident Ledger must be before hiding a suspected
  duplicate. Lower catches more, but may hide genuine repeat purchases.

**Save & re-run** applies the new rules. Matches you confirmed or rejected are kept.
