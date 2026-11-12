// Contract types mirroring backend/src/ledger/api/serializers.py

export type Role = "income" | "expense" | "investment" | "transfer" | "adjustment";
export const ROLES: Role[] = ["income", "expense", "investment", "transfer", "adjustment"];
export const ROLE_LABEL: Record<Role, string> = {
  income: "Income",
  expense: "Expenses",
  investment: "Investments",
  transfer: "Financial movements",
  adjustment: "Adjustments",
};

export interface GeneralSettings {
  country: string | null;
  base_currency: string | null;
  locale: string;
  timezone: string;
  date_format: string;
  decimal_separator: string;
  thousands_separator: string;
  onboarding_complete: boolean;
}

export interface IngestionSettings {
  watch_folder: string | null;
  watch_enabled: boolean;
  poll_seconds: number;
}

export interface ReconciliationSettings {
  transfer_window_days: number;
  settlement_window_days: number;
  refund_window_days: number;
  duplicate_min_confidence: number;
}

export interface Settings {
  general: GeneralSettings;
  ingestion: IngestionSettings;
  reconciliation: ReconciliationSettings;
  config_version: number;
}

export interface Identity {
  id: number;
  display_name: string;
  legal_name: string | null;
  kind: "individual" | "household";
  identifiers: string[];
  aliases: { id: number; alias: string }[];
}

export interface Institution {
  id: number;
  name: string;
  aliases: string[];
  country: string | null;
}

export const ACCOUNT_TYPES = [
  "savings",
  "current",
  "credit_card",
  "investment",
  "brokerage",
  "fixed_deposit",
  "loan",
  "cash",
  "other",
] as const;
export type AccountType = (typeof ACCOUNT_TYPES)[number];

export interface Account {
  id: number;
  name: string;
  account_type: AccountType;
  institution_id: number | null;
  institution: string | null;
  masked_number: string | null;
  currency: string;
  aliases: string[];
  auto_discovered: boolean;
  active: boolean;
  owners: { identity_id: number; source: string; confidence: number }[];
  transaction_count?: number;
  last_transaction?: string | null;
  last_balance?: string | null;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
  description: string;
  parent_id: number | null;
  role: Role;
  is_system: boolean;
  active: boolean;
  merged_into_id: number | null;
  semantic_version: number;
  sort_order: number;
  transaction_count?: number;
}

export interface MerchantAlias {
  id: number;
  pattern: string;
  match_type: "key" | "contains" | "regex";
  source: string;
}

export interface Merchant {
  id: number;
  canonical_name: string;
  description: string;
  default_category_id: number | null;
  source: "user" | "auto" | "llm";
  aliases: MerchantAlias[];
  transaction_count?: number;
}

export interface Rule {
  id: number;
  name: string;
  priority: number;
  conditions: {
    description_contains?: string[];
    description_regex?: string;
    direction?: "inflow" | "outflow";
    account_ids?: number[];
    account_types?: string[];
    merchant_ids?: number[];
    min_amount?: string;
    max_amount?: string;
  };
  actions: { category?: string; owner_identity_id?: number };
  source: "user" | "system" | "learned";
  confidence: number;
  active: boolean;
}

export interface DocumentInfo {
  id: number;
  original_filename: string;
  file_format: string;
  size_bytes: number;
  status: "queued" | "processing" | "processed" | "failed" | "duplicate";
  error: string | null;
  warnings: string[];
  institution: string | null;
  account_id: number | null;
  account: string | null;
  document_type: string | null;
  statement_start: string | null;
  statement_end: string | null;
  currency: string | null;
  opening_balance: string | null;
  closing_balance: string | null;
  extraction_method: string | null;
  identification: Record<string, unknown>;
  stats: {
    rows?: number;
    inserted?: number;
    duplicates_across_documents?: number;
    duplicates_within_document?: number;
    classification?: { by_method?: Record<string, number>; ai_calls?: number };
    reconciliation?: Record<string, number>;
  };
  source_path: string | null;
  created_at: string;
}

export interface Txn {
  id: number;
  account_id: number;
  account: string | null;
  account_type: string | null;
  document_id: number | null;
  txn_date: string;
  posting_date: string | null;
  description_raw: string;
  amount: string;
  currency: string;
  base_amount: string | null;
  direction: "inflow" | "outflow";
  reference: string | null;
  balance_after: string | null;
  category_id: number | null;
  category: string | null;
  role: Role | null;
  merchant_id: number | null;
  merchant: string | null;
  owner_identity_id: number | null;
  is_recurring: boolean;
  classification_method: string | null;
  classification_confidence: number | null;
  pinned_fields: string[];
  duplicate_of_id: number | null;
  entry_method: string;
}

export interface Link {
  id: number;
  kind: "internal_transfer" | "card_settlement" | "refund" | "duplicate";
  from_transaction_id: number;
  to_transaction_id: number;
  confidence: number;
  method: string;
  evidence: Record<string, unknown>;
  status: "auto" | "confirmed" | "rejected";
  history: Record<string, unknown>[];
  created_at: string;
  from?: Txn | null;
  to?: Txn | null;
  counterpart?: Txn | null;
}

export interface TxnDetail extends Txn {
  description_normalized: string;
  source_ref: Record<string, unknown>;
  raw: Record<string, unknown>;
  classification_evidence: Record<string, unknown>;
  classification_config_version: number | null;
  document: { id: number; filename: string; institution: string | null } | null;
  links: Link[];
  history: {
    at: string;
    method: string;
    category: string | null;
    confidence: number | null;
    evidence: Record<string, unknown>;
    config_version: number | null;
    model: string | null;
    provider: string | null;
  }[];
  overrides: { at: string; field: string; old: unknown; new: unknown; apply_to_similar: boolean }[];
}

export interface Metrics {
  total_inflows: string;
  total_outflows: string;
  external_inflows: string;
  external_outflows: string;
  net_cash_flow: string;
  income: string;
  consumption: string;
  refunds: string;
  investment_outflows: string;
  investment_inflows: string;
  net_invested: string;
  transfers: string;
  savings_rate: string | null;
}

export interface SeriesPoint extends Metrics {
  period: string;
}

export interface Overview {
  metrics: Metrics;
  transaction_count: number;
  unconverted_count: number;
  low_confidence_count: number;
  date_range: [string | null, string | null];
  series: SeriesPoint[];
}

export interface CategoryTotal {
  category_id: number | null;
  slug: string | null;
  name: string;
  parent: string | null;
  role: Role | null;
  total: string;
  count: number;
  period?: string;
}

export interface MerchantTotal {
  merchant_id: number;
  name: string;
  total: string;
  count: number;
  recurring: boolean;
  first: string;
  last: string;
}

export interface ProviderConfig {
  id: string;
  kind: "api" | "local" | "cli";
  label?: string | null;
  model?: string | null;
  api_base?: string | null;
  cli?: "claude" | "codex" | null;
  executable?: string | null;
  extra_args?: string[];
  timeout_s?: number;
  max_tokens?: number;
  temperature?: number;
  enabled?: boolean;
  has_key?: boolean | null;
}

export interface IntelligenceConfig {
  providers: ProviderConfig[];
  routing: Record<string, string[]>;
  allow_cloud: boolean;
  share_identity_names: boolean;
  batch_size: number;
  tasks: Record<string, string>;
  templates: Partial<ProviderConfig & { label: string }>[];
}

export interface Job {
  id: number;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  attempts: number;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
  payload: Record<string, unknown>;
}

export interface ConfigChange {
  id: number;
  scope: string;
  version: number;
  global_version: number;
  action: string;
  summary: string;
  propagation: "none" | "deterministic" | "ai";
  created_at: string;
}

export interface AnalyticsFilters {
  date_from?: string;
  date_to?: string;
  identity_id?: number;
  scope?: "household" | "individual" | "joint";
  account_id?: number[];
}
