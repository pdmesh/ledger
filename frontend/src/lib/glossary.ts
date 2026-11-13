// Plain-language explanations for the ledger's own vocabulary, shown in help tooltips.
// Keep each to one or two sentences; the UI shows them on hover/focus.

export const GLOSSARY = {
  // Reconciliation: kinds of relationship between two transactions
  internal_transfer:
    "Money moved between two of your own accounts (e.g. savings → checking). Both sides are kept but counted as a financial movement, not income or spending.",
  card_settlement:
    "A payment from a bank account that pays off a credit card bill. Linking it stops the bill payment being counted as spending on top of the card purchases themselves.",
  refund:
    "Money returned for an earlier purchase. Linked refunds reduce what that purchase counts as spending.",
  duplicate:
    "The same transaction imported twice, e.g. from overlapping statements. The copy is hidden from totals but never deleted.",

  // Reconciliation: link status and method
  link_auto: "Matched automatically and in effect, but not yet checked by you. Confirm or reject it to settle it.",
  link_confirmed: "You confirmed this match. Later re-runs keep it.",
  link_rejected:
    "You rejected this match. Both transactions are classified independently again, and the pair is never re-linked.",
  method_deterministic: "Matched by fixed rules: amounts, dates within the matching window, and accounts.",
  method_llm: "Several candidates looked plausible, so an AI provider chose between them.",
  method_user: "Set by you.",
  match_confidence: "How sure the matcher is that these two transactions belong together.",

  // Reconciliation settings
  transfer_window: "How many days apart the two sides of a transfer between your accounts may be.",
  settlement_window: "How many days after a card statement a bank payment can still be matched as paying that card's bill.",
  refund_window: "How long after a purchase a refund from the same merchant can be matched to it.",
  duplicate_threshold: "Minimum match confidence before a suspected duplicate is hidden. Lower catches more but risks hiding real repeats.",

  // Classification methods (how a category was decided)
  classification_confidence:
    "How certain the ledger is about the category. Below 50% is worth checking; your own corrections show as “You”.",
  user: "You set this yourself. It's pinned, so automatic re-classification won't change it.",
  rule: "Matched one of your classification rules.",
  merchant_map: "This merchant has a default category you (or an earlier decision) set.",
  history: "Chosen from how you've categorised this merchant before.",
  llm: "Chosen by an AI provider.",
  reconciliation: "Set by reconciliation, e.g. a transfer or card payment.",
  fallback: "Nothing matched, so it was left uncategorised with low confidence.",

  // Configuration history
  propagation_deterministic:
    "This change was also applied to transactions you already have, using rules and mappings only (no AI). Pinned values you set by hand are left alone.",
  propagation_ai:
    "This change altered what a category means, so affected transactions are re-classified in the background, including by your AI providers.",
  config_version: "Every settings change creates a new version. Each transaction records which version classified it.",

  // Intelligence
  allow_cloud:
    "Cloud APIs and CLI tools (Claude Code, Codex) receive transaction descriptions and amounts for categorisation. When a statement has to be read by AI (layouts the built-in parser can't handle, or scanned PDFs), the whole statement is sent as it is: names, account numbers and addresses included. Local models (Ollama etc.) are always allowed.",
  share_names:
    "Off: household members' names are replaced by “Person 1”, “Person 2” in categorisation and matching requests. This can't apply when a whole statement is read by AI: the statement text or page images are sent unchanged.",
  task_routing:
    "Which provider handles each kind of work. Providers are tried in order: if one fails, times out or returns unusable output, the next one (“then …”) is tried.",
  cli_default:
    "CLI default is the CLI's built-in default model. The app runs Claude Code sandboxed, which skips your Claude Code settings files, so a model set there isn't used. Pick a model here to control which one (and its cost).",

  // Overview metrics
  consumption: "Spending on goods and services, after refunds. Excludes transfers, card bill payments and investments.",
  net_invested: "Money put into investments minus money taken out of them.",
  net_cash_flow: "Money that came from outside your accounts minus money that left them. Transfers between your own accounts cancel out.",
  savings_rate: "Share of income not spent on consumption: (income − consumption) ÷ income.",
  financial_movements: "Transfers between your accounts and credit card bill payments. They move money around but aren't spending.",

  // Import
  money_in_out:
    "Totals of the rows imported from this statement. For a card, “Money out” should match the purchases on the bill; “Money in” is usually last month's payment and refunds.",
  doc_duplicate: "This exact file was imported before, so nothing new was added.",
  needs_password:
    "This PDF is password-protected. Enter its password to import it. Nothing is read or sent anywhere until then.",
  remember_password:
    "Banks and card issuers usually reuse one password per person, so remembered passwords are tried automatically on future protected statements. They're kept in your OS keychain, never in the ledger database.",
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
