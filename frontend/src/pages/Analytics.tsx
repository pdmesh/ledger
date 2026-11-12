import { Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import type { NavTarget } from "../App";
import { StackedTrend } from "../components/charts";
import { Badge, Button, Card, ErrorNote, Input, Select, Tabs, cn } from "../components/ui";
import { api } from "../lib/api";
import { useApp } from "../lib/context";
import { date, money, num, pct } from "../lib/format";
import { useApi } from "../lib/hooks";
import { ROLES, ROLE_LABEL, type CategoryTotal, type MerchantTotal, type Metrics, type Role, type SeriesPoint } from "../lib/types";

type Tab = "categories" | "merchants" | "household" | "compare" | "ask";

export default function AnalyticsPage({ go }: { go: (t: NavTarget) => void }) {
  const [tab, setTab] = useState<Tab>("categories");
  return (
    <div className="space-y-4">
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "categories", label: "Categories" },
          { value: "merchants", label: "Merchants" },
          { value: "household", label: "Household" },
          { value: "compare", label: "Period comparison" },
          { value: "ask", label: "Ask" },
        ]}
      />
      {tab === "categories" && <Categories go={go} />}
      {tab === "merchants" && <Merchants go={go} />}
      {tab === "household" && <Household />}
      {tab === "compare" && <Compare />}
      {tab === "ask" && <Ask />}
    </div>
  );
}

function sign(role: Role) {
  // outflow-heavy roles are shown as positive magnitudes
  return role === "expense" || role === "investment" || role === "transfer" ? -1 : 1;
}

function Categories({ go }: { go: (t: NavTarget) => void }) {
  const { filters } = useApp();
  const [role, setRole] = useState<Role>("expense");
  const [gran, setGran] = useState("month");
  const series = useApi<CategoryTotal[]>("/analytics/categories", { ...filters, role, granularity: gran });
  const totals = useApi<CategoryTotal[]>("/analytics/categories", { ...filters, role });

  const { rows, keys } = useMemo(() => {
    const s = sign(role);
    const top = (totals.data ?? []).slice(0, 7).map((c) => c.name);
    const byPeriod = new Map<string, Record<string, number | string>>();
    for (const c of series.data ?? []) {
      const p = c.period!;
      const row = byPeriod.get(p) ?? { period: p };
      const key = top.includes(c.name) ? c.name : "Other";
      row[key] = (Number(row[key]) || 0) + s * num(c.total);
      byPeriod.set(p, row);
    }
    const ks = [...top];
    if ((totals.data ?? []).length > 7) ks.push("Other");
    return { rows: [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period))), keys: ks };
  }, [series.data, totals.data, role]);

  const grand = (totals.data ?? []).reduce((a, c) => a + sign(role) * num(c.total), 0);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
        <Select value={gran} onChange={(e) => setGran(e.target.value)}>
          <option value="month">Monthly</option>
          <option value="quarter">Quarterly</option>
          <option value="year">Yearly</option>
        </Select>
      </div>
      <Card title={`${ROLE_LABEL[role]} by category over time`}>
        <StackedTrend rows={rows} keys={keys} />
      </Card>
      <Card title="Totals">
        <table className="w-full text-sm">
          <tbody>
            {(totals.data ?? []).map((c) => {
              const v = sign(role) * num(c.total);
              return (
                <tr key={c.category_id ?? "none"} className="border-b border-border/60 last:border-0">
                  <td className="py-1.5">
                    <button className="hover:underline" onClick={() => c.category_id && go({ section: "transactions", txnFilter: { category_id: [c.category_id] } })}>
                      {c.parent ? `${c.parent} › ` : ""}
                      {c.name}
                    </button>
                  </td>
                  <td className="num py-1.5 text-right text-fg-muted">{c.count}</td>
                  <td className="num py-1.5 text-right">{money(v)}</td>
                  <td className="num w-20 py-1.5 text-right text-fg-subtle">{grand ? pct(v / grand) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Merchants({ go }: { go: (t: NavTarget) => void }) {
  const { filters } = useApp();
  const [role, setRole] = useState<Role>("expense");
  const res = useApi<MerchantTotal[]>("/analytics/merchants", { ...filters, role, limit: 100 });
  return (
    <div className="space-y-3">
      <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r]}
          </option>
        ))}
      </Select>
      <Card>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-fg-muted">
            <tr>
              <th className="pb-2 font-medium">Merchant</th>
              <th className="pb-2 text-right font-medium">Transactions</th>
              <th className="pb-2 text-right font-medium">Average</th>
              <th className="pb-2 text-right font-medium">Total</th>
              <th className="pb-2 pl-4 font-medium">Active</th>
            </tr>
          </thead>
          <tbody>
            {(res.data ?? []).map((m) => (
              <tr key={m.merchant_id} className="border-t border-border/60">
                <td className="py-1.5">
                  <button className="hover:underline" onClick={() => go({ section: "transactions", txnFilter: { merchant_id: [m.merchant_id] } })}>
                    {m.name}
                  </button>
                  {m.recurring && <Badge className="ml-2">recurring</Badge>}
                </td>
                <td className="num py-1.5 text-right">{m.count}</td>
                <td className="num py-1.5 text-right text-fg-muted">{money(Math.abs(num(m.total)) / m.count)}</td>
                <td className="num py-1.5 text-right">{money(Math.abs(num(m.total)))}</td>
                <td className="num py-1.5 pl-4 text-xs text-fg-subtle">
                  {date(m.first)} – {date(m.last)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

const METRIC_ROWS: { key: keyof Metrics; label: string }[] = [
  { key: "income", label: "Income" },
  { key: "consumption", label: "Consumption" },
  { key: "net_invested", label: "Invested (net)" },
  { key: "net_cash_flow", label: "Net cash flow" },
  { key: "transfers", label: "Financial movements" },
  { key: "savings_rate", label: "Savings rate" },
];

function Household() {
  const { filters } = useApp();
  const res = useApi<{ identity_id: number | null; name: string; metrics: Metrics; transaction_count: number }[]>("/analytics/household", {
    date_from: filters.date_from,
    date_to: filters.date_to,
  });
  return (
    <Card title="Household members">
      <p className="mb-3 text-xs text-fg-muted">
        Individual views include each person's own and joint accounts, so joint activity appears under each owner; the household view
        counts every transaction exactly once.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-fg-muted">
            <tr>
              <th className="pb-2 font-medium" />
              {(res.data ?? []).map((h) => (
                <th key={h.name} className="pb-2 text-right font-medium">
                  {h.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {METRIC_ROWS.map((r) => (
              <tr key={r.key} className="border-t border-border/60">
                <td className="py-1.5 text-fg-muted">{r.label}</td>
                {(res.data ?? []).map((h) => (
                  <td key={h.name} className="num py-1.5 text-right">
                    {r.key === "savings_rate" ? pct(h.metrics[r.key]) : money(h.metrics[r.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Delta({ cur, prev, invert }: { cur: number; prev: number | undefined; invert?: boolean }) {
  if (prev === undefined || prev === 0) return <span className="text-fg-subtle">—</span>;
  const d = (cur - prev) / Math.abs(prev);
  const good = invert ? d < 0 : d > 0;
  return <span className={cn("num", good ? "text-positive" : "text-negative")}>{`${d > 0 ? "+" : ""}${(d * 100).toFixed(0)}%`}</span>;
}

function Compare() {
  const { view, filters } = useApp();
  const [gran, setGran] = useState<"month" | "quarter" | "year">("month");
  const [metric, setMetric] = useState<keyof Metrics>("consumption");
  const res = useApi<SeriesPoint[]>("/analytics/timeseries", { scope: filters.scope, identity_id: filters.identity_id, granularity: gran });
  const rows = res.data ?? [];
  const byPeriod = new Map(rows.map((r) => [r.period, num(r[metric])]));
  const lastYear = (p: string) => (gran === "year" ? String(Number(p) - 1) : `${Number(p.slice(0, 4)) - 1}${p.slice(4)}`);
  const invert = metric === "consumption";
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Select value={metric} onChange={(e) => setMetric(e.target.value as keyof Metrics)}>
          {METRIC_ROWS.filter((m) => m.key !== "savings_rate").map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </Select>
        <Select value={gran} onChange={(e) => setGran(e.target.value as typeof gran)}>
          <option value="month">Month over month</option>
          <option value="quarter">Quarter over quarter</option>
          <option value="year">Year over year</option>
        </Select>
        <span className="self-center text-xs text-fg-subtle">{view.preset !== "all" && "Uses all history regardless of period filter."}</span>
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-fg-muted">
            <tr>
              <th className="pb-2 font-medium">Period</th>
              <th className="pb-2 text-right font-medium">Value</th>
              <th className="pb-2 text-right font-medium">vs previous</th>
              {gran !== "year" && <th className="pb-2 text-right font-medium">vs last year</th>}
            </tr>
          </thead>
          <tbody>
            {[...rows].reverse().map((r, i, arr) => (
              <tr key={r.period} className="border-t border-border/60">
                <td className="py-1.5">{r.period}</td>
                <td className="num py-1.5 text-right">{money(r[metric])}</td>
                <td className="py-1.5 text-right">
                  <Delta cur={num(r[metric])} prev={arr[i + 1] ? num(arr[i + 1][metric]) : undefined} invert={invert} />
                </td>
                {gran !== "year" && (
                  <td className="py-1.5 text-right">
                    <Delta cur={num(r[metric])} prev={byPeriod.get(lastYear(r.period))} invert={invert} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Ask() {
  const { filters } = useApp();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<{ answer: string; table: (string | number)[][] | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api.post("/analytics/ask", { question: q }, { ...filters }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title={<span className="flex items-center gap-2"><Sparkles size={14} /> Ask about your finances</span>}>
      <p className="mb-3 text-xs text-fg-muted">
        Answers are generated from aggregated figures (totals by month, category and merchant) — never raw statements — using the model
        routed to the “query” task in Settings.
      </p>
      <div className="flex gap-2">
        <Input value={q} placeholder="How did our dining spend change compared with last quarter?" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && q && ask()} />
        <Button onClick={ask} disabled={!q || busy}>
          {busy ? "Thinking…" : "Ask"}
        </Button>
      </div>
      <div className="mt-4 space-y-3">
        <ErrorNote error={error} />
        {answer && <p className="whitespace-pre-wrap text-sm leading-relaxed">{answer.answer}</p>}
        {answer?.table && (
          <table className="text-sm">
            <tbody>
              {answer.table.map((row, i) => (
                <tr key={i} className="border-t border-border/60">
                  {row.map((c, j) => (
                    <td key={j} className="py-1 pr-4">
                      {String(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}
