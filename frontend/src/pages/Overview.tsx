import { AlertTriangle } from "lucide-react";
import type { NavTarget } from "../App";
import { BarList, CashFlowChart, ROLE_COLOR } from "../components/charts";
import { Card, Empty, ErrorNote, Help } from "../components/ui";
import type { GlossaryKey } from "../lib/glossary";
import { useApp } from "../lib/context";
import { money, num, pct } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { CategoryTotal, MerchantTotal, Overview } from "../lib/types";

function Stat({ label, value, sub, tone, help }: { label: string; value: string; sub?: string; tone?: keyof typeof ROLE_COLOR; help?: GlossaryKey }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <p className="flex items-center gap-1.5 text-xs text-fg-muted">
        {tone && <span className="h-2 w-2 rounded-sm" style={{ background: ROLE_COLOR[tone] }} />}
        {label}
        {help && <Help term={help} />}
      </p>
      <p className="num mt-1 text-xl font-semibold tracking-tight">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-fg-subtle">{sub}</p>}
    </div>
  );
}

export default function OverviewPage({ go }: { go: (t: NavTarget) => void }) {
  const { filters } = useApp();
  const q = { ...filters };
  const ov = useApi<Overview>("/analytics/overview", q);
  const cats = useApi<CategoryTotal[]>("/analytics/categories", { ...q, role: "expense" });
  const merchants = useApi<MerchantTotal[]>("/analytics/merchants", { ...q, limit: 8 });

  if (ov.error) return <ErrorNote error={ov.error} />;
  const o = ov.data;
  if (!o) return null;
  if (o.transaction_count === 0) {
    return (
      <Empty title="No transactions yet">
        Drop bank and credit-card statements (PDF, CSV, XLSX) into the Import Centre, or set a watched folder. Everything
        is processed on this device.
      </Empty>
    );
  }
  const m = o.metrics;
  const topCats = (cats.data ?? [])
    .filter((c) => c.role === "expense" || c.role === null)
    .slice(0, 8)
    .map((c) => ({ key: c.category_id ?? 0, label: c.parent ? `${c.parent} › ${c.name}` : c.name, value: -num(c.total), hint: `${c.count} transactions` }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-6">
        <Stat label="Income" value={money(m.income)} tone="income" />
        <Stat help="consumption" label="Consumption" value={money(m.consumption)} sub={num(m.refunds) ? `after ${money(m.refunds)} refunds` : undefined} tone="expense" />
        <Stat help="net_invested" label="Invested (net)" value={money(m.net_invested)} sub={`${money(m.investment_outflows)} in · ${money(m.investment_inflows)} out`} tone="investment" />
        <Stat help="net_cash_flow" label="Net cash flow" value={money(m.net_cash_flow)} sub="external in − external out" />
        <Stat help="savings_rate" label="Savings rate" value={pct(m.savings_rate)} sub="(income − consumption) / income" />
        <Stat help="financial_movements" label="Financial movements" value={money(m.transfers)} sub="transfers & card settlements, not spending" tone="transfer" />
      </div>

      {(o.low_confidence_count > 0 || o.unconverted_count > 0) && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-surface px-4 py-2.5 text-sm">
          <AlertTriangle size={15} className="text-warning" />
          {o.low_confidence_count > 0 && (
            <button className="underline-offset-2 hover:underline" onClick={() => go({ section: "transactions", txnFilter: { max_confidence: 0.5 } })}>
              {o.low_confidence_count} low-confidence classifications
            </button>
          )}
          {o.unconverted_count > 0 && (
            <span className="text-fg-muted">{o.unconverted_count} foreign-currency transactions lack an exchange rate and are excluded from totals</span>
          )}
        </div>
      )}

      <Card title="Cash flow by month">
        <CashFlowChart data={o.series} />
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Where the money goes">
          {topCats.length ? (
            <BarList items={topCats} color={ROLE_COLOR.expense} onClick={(k) => go({ section: "transactions", txnFilter: { category_id: [Number(k)] } })} />
          ) : (
            <p className="text-sm text-fg-muted">No consumption in this period.</p>
          )}
        </Card>
        <Card title="Top merchants">
          <BarList
            items={(merchants.data ?? []).map((mm) => ({
              key: mm.merchant_id,
              label: mm.name,
              value: -num(mm.total),
              hint: `${mm.count}×${mm.recurring ? " · recurring" : ""}`,
            }))}
            onClick={(k) => go({ section: "transactions", txnFilter: { merchant_id: [Number(k)] } })}
          />
        </Card>
      </div>
    </div>
  );
}
