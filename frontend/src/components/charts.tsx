import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, num } from "../lib/format";

const AXIS = { fontSize: 11, fill: "var(--color-fg-subtle)" };
const GRID = "var(--color-border)";

export const ROLE_COLOR = {
  income: "var(--color-role-income)",
  expense: "var(--color-role-expense)",
  investment: "var(--color-role-investment)",
  transfer: "var(--color-role-transfer)",
  adjustment: "var(--color-role-adjustment)",
} as const;

// Categorical palette for category trends (validated against light and dark surfaces).
export const PALETTE = ["#2f5bd3", "#c8372d", "#1f8a4c", "#b26a00", "#6b4fd6", "#0e8a8a", "#c2418f", "#5e5e58"];

function TooltipBox({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="num">{money(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

export function CashFlowChart({ data }: { data: { period: string; income: string; consumption: string; investment_outflows: string; net_cash_flow: string }[] }) {
  const rows = data.map((d) => ({
    period: d.period,
    Income: num(d.income),
    Consumption: num(d.consumption),
    Invested: num(d.investment_outflows),
    "Net cash flow": num(d.net_cash_flow),
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="period" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={64} tickFormatter={(v) => money(v, undefined, true)} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--color-muted)" }} />
        <Legend wrapperStyle={{ fontSize: 12 }} iconType="square" iconSize={8} />
        <Bar dataKey="Income" fill={ROLE_COLOR.income} radius={[2, 2, 0, 0]} maxBarSize={22} />
        <Bar dataKey="Consumption" fill={ROLE_COLOR.expense} radius={[2, 2, 0, 0]} maxBarSize={22} />
        <Bar dataKey="Invested" fill={ROLE_COLOR.investment} radius={[2, 2, 0, 0]} maxBarSize={22} />
        <Line dataKey="Net cash flow" stroke="var(--color-fg)" strokeWidth={1.5} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function StackedTrend({ rows, keys }: { rows: Record<string, string | number>[]; keys: string[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="period" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={64} tickFormatter={(v) => money(v, undefined, true)} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--color-muted)" }} />
        <Legend wrapperStyle={{ fontSize: 12 }} iconType="square" iconSize={8} />
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} stackId="a" fill={PALETTE[i % PALETTE.length]} maxBarSize={28} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal magnitude bars (simple, readable alternative to pies). */
export function BarList({ items, onClick, color = "var(--color-accent)" }: { items: { label: string; value: number; hint?: string; key: string | number }[]; onClick?: (key: string | number) => void; color?: string }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  return (
    <ul className="space-y-1.5">
      {items.map((it) => (
        <li key={it.key}>
          <button
            className="group w-full text-left disabled:cursor-default"
            disabled={!onClick}
            onClick={() => onClick?.(it.key)}
          >
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="truncate group-hover:underline">{it.label}</span>
              <span className="num shrink-0 text-fg-muted">{money(it.value)}</span>
            </div>
            <div className="mt-0.5 h-1.5 rounded-full bg-muted">
              <div className="h-1.5 rounded-full" style={{ width: `${(Math.abs(it.value) / max) * 100}%`, background: color }} />
            </div>
            {it.hint && <p className="mt-0.5 text-[11px] text-fg-subtle">{it.hint}</p>}
          </button>
        </li>
      ))}
    </ul>
  );
}
