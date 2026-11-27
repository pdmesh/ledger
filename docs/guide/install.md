---
title: Install and set up
---

# Install and set up

[← User guide](index.md)

## Download

Download the latest `.dmg` from the
[releases page](https://github.com/pdmesh/ledger/releases/latest).

The 0.1 release is built for **Macs with Apple silicon** (M1 and later). Windows, Linux
and Intel Mac users can run Ledger from source; see the
[README](https://github.com/pdmesh/ledger#getting-started).

## First launch on macOS

Ledger isn't signed with an Apple Developer ID yet, so macOS asks you to confirm the first
time you open it.

1. Open the `.dmg` and drag **Ledger** into **Applications**.
2. Open Ledger from Applications. macOS says it can't verify the developer; choose **Done**.
3. Open **System Settings → Privacy & Security**, scroll to the message about Ledger and
   choose **Open Anyway**, then confirm.

If macOS instead says the app "is damaged", the download was quarantined. Run this once in
Terminal, then open Ledger again:

```bash
xattr -dr com.apple.quarantine /Applications/Ledger.app
```

The first start takes a little longer while macOS checks the bundled files. You'll see
"Starting the local backend…" until it's ready.

## Set up your household

The first screen asks for:

- **Country and base currency.** Sets the default date format, currency and number style.
  Totals are shown in the base currency; accounts in other currencies are converted with
  the exchange rates you enter under **Settings → General → Exchange rates**.
- **Who is in your household.** Add each person and the ways their name appears on
  statements (for example "A Sample" or "Alex S"). Ledger uses these to work out whose
  account each statement belongs to, and joint accounts get several owners.

You can change all of this later under **Settings → General** and **Settings → People &
identities**.

## Updating

Download the new `.dmg` and replace the app in Applications. Your data is kept separately
(see [Privacy, backups and your data](privacy.md)) and is migrated automatically on the
next start. Make a backup first if you want to be able to go back.

## Uninstalling

Delete Ledger from Applications. Your ledger, archived statements and backups stay in
`~/Library/Application Support/dev.personal-ledger.app` until you delete that folder too.
API keys and PDF passwords are in your keychain under the service name
`personal-ledger`; remove them with Keychain Access if you no longer need them.
