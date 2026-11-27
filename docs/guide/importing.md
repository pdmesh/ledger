---
title: Import statements
---

# Import statements

[← User guide](index.md)

## What you can import

Bank, credit card and investment-account statements as **PDF, CSV, XLSX or XLS**. Ledger
works out which institution and account a statement belongs to, the statement period and
whose account it is, and creates the account the first time it sees it.

Importing the same file twice does nothing, and statements whose dates overlap are fine:
repeated rows are recognised as duplicates and hidden from totals.

## Importing

Open **Import Centre** and either drop files onto the drop zone or click it to choose
files. Each file appears in the list and goes from *queued* to *processing* to
*processed*.

To import automatically, set a **Watched folder** (for example the folder your bank
downloads go to), turn on **Watch**, and Ledger picks up new files as they appear. **Scan
now** checks the folder straight away.

## How a statement is read

1. Ledger first reads the statement itself, looking for the table of transactions.
2. If it can't find one (an unusual layout), and you've set up an
   [AI provider](ai-providers.md) for reading statements, the statement is sent to that
   model to extract the transactions.
3. **Scanned PDFs**, which are just pictures of pages, are always read by an AI model
   that understands images. Up to 12 pages are read; a longer statement shows a warning
   saying how many pages were skipped.

A statement read by AI shows a warning reminding you to check it against the original.
The **Money in** and **Money out** columns make that quick (see below).

## Password-protected PDFs

Many banks lock statements with a password. A locked statement shows as **locked** with
an **Enter password** button. Nothing is read, and nothing is sent anywhere, until you
unlock it.

- The password is checked immediately, so you'll know at once if it's wrong.
- It's stored in your macOS keychain, never in the ledger database.
- With **Try this password on future protected statements** ticked (the default), Ledger
  tries it on every new locked statement, including ones from the watched folder, and
  retries any others that are waiting. Banks usually reuse one password per person, so
  you'll rarely be asked twice.

## Checking an import

The Import Centre list shows, for each statement, the number of transactions and the
**Money in** and **Money out** totals. For a credit card, **Money out** should match the
purchases on the bill. **Money in** is usually last month's payment and any refunds.

Click a statement to see its details: the institution and account it was matched to, the
period, the balances, any warnings, and **Open original**, which opens the archived file in
your usual PDF or spreadsheet app.

## Warnings

| Warning | What it means |
|---|---|
| Extracted by AI; verify against the original | The layout wasn't recognised, so a model read it. Compare the totals. |
| N transaction(s) fall outside the statement period | Some dates look wrong, or the period wasn't detected. |
| Statement totals do not reconcile | Opening balance plus transactions doesn't equal the closing balance; a row may be missing or misread. |
| Running balance does not chain on N row(s) | The balance column jumps; usually a misread amount or sign. |
| Only the first 12 of N pages were read | A long scanned statement; later transactions are missing. |

## Re-processing and deleting

- **Re-process** reads the statement again, for example after you set up an AI provider.
  It's refused if you've corrected any of its transactions, so your edits aren't lost.
- **Delete** removes the statement, its archived file and every transaction imported from
  it, including categories you set on them. Ledger tells you how many transactions will go
  before you confirm. If another statement contained the same transactions, its copies
  become the live ones, so you never end up with none. Use this to undo an accidental
  import.
