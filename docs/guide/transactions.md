---
title: Work with transactions
---

# Work with transactions

[← User guide](index.md)

## Finding transactions

**Transactions** lists everything, newest first. Narrow it down with:

- the search box (description or reference),
- type (income, expenses, investments, financial movements, adjustments), category,
  account and statement,
- money in or money out,
- reconciliation (linked, unlinked, duplicates) and confidence.

The bar at the top of the window sets whose finances you're looking at (the whole
household or one person) and the period.

## Totals

The bar at the bottom adds up **every transaction matching your filters**, not just the
page on screen: the count, money in, money out and net. **By statement** breaks the same
totals down by the statement each transaction came from; click a row to show only that
statement. The eye icon hides the bar and **Totals** brings it back.

A quick way to check a card import: filter to **Money out**, open **By statement**, and
compare the figure with your bill.

## How sure Ledger is

The **Confidence** column shows how certain the category is, and hovering it says how it
was chosen:

| Shown as | Meaning |
|---|---|
| You | You set it. It's pinned and won't change automatically. |
| Rule | One of your classification rules matched. |
| Merchant map | This merchant has a default category. |
| History | Based on how you've categorised this merchant before. |
| AI | Chosen by your AI provider. |
| Reconciliation | Set because it's a transfer, card payment or refund. |
| Fallback | Nothing matched; it's uncategorised. |

Filter by **Low confidence** to find the ones worth a look.

## Fixing a category

Click a transaction to open its details and pick a new category, merchant or owner. Your
choice is **pinned**: it won't be changed by later re-classification, and Ledger learns
from it for that merchant. To hand a field back to automatic classification, use the
release link next to the pinned value.

The details panel also shows where the transaction came from (statement, page and row),
the values extracted from it, and its history.

## Adding a transaction by hand

For money that no statement covers, like cash, choose **Add** on the Transactions page.
Pick the account, date, description, amount and whether it's money in or out. Leave the
category on **Classify automatically** or choose one. A transaction you entered by hand
can be deleted from its details panel; imported ones are removed by deleting their
statement.

## Categories, merchants and rules

Under **Settings**:

- **Taxonomy**: rename, describe, move, merge or add categories. Changes apply to existing
  transactions too; the **Privacy & data** tab lists each change.
- **Merchants**: merge merchants that are really the same and set a default category.
- **Classification rules**: "if the description contains … then category …" rules, for
  anything the automatic categorising gets wrong repeatedly.

## Analytics

**Overview** shows income, spending, investments, net cash flow and savings rate for the
selected period. **Analytics** breaks spending down by category, merchant and household
member, and compares periods. Hover the help icons for what each figure includes. With an
AI provider set up, **Analytics → Ask** answers questions about your finances from these
summary figures.
