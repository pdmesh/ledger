import { Pin, Repeat } from "lucide-react";
import { useEffect, useState } from "react";
import { TransactionDetail } from "../components/TransactionDetail";
import { Badge, Button, Confidence, Drawer, ErrorNote, Input, Select, cn } from "../components/ui";
import { categoryPath, useApp } from "../lib/context";
import { date, humanize, money } from "../lib/format";
import { useApi } from "../lib/hooks";
import { ROLES, ROLE_LABEL, type Txn } from "../lib/types";

type Filter = Record<string, string | number | (string | number)[] | undefined>;

const PAGE = 100;

export default function TransactionsPage({ initialFilter }: { initialFilter?: Filter }) {
  const { filters, accounts, categories, identities } = useApp();
  const [f, setF] = useState<Filter>(initialFilter ?? {});
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => setF(initialFilter ?? {}), [initialFilter]);
  useEffect(() => setOffset(0), [f, q, filters]);

  const query = { ...filters, ...f, q, limit: PAGE, offset };
  const res = useApi<{ total: number; items: Txn[] }>("/transactions", query);
  const set = (k: string, v: string | number | (string | number)[] | undefined) =>
    setF((prev) => ({ ...prev, [k]: v === "" ? undefined : v }));
  const owner = (id: number | null) => identities.find((i) => i.id === id)?.display_name;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input className="w-64" placeholder="Search description or reference" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={(f.role as string[] | undefined)?.[0] ?? ""} onChange={(e) => set("role", e.target.value ? [e.target.value] : undefined)}>
          <option value="">All types</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
        <Select
          value={(f.category_id as number[] | undefined)?.[0] ?? ""}
          onChange={(e) => set("category_id", e.target.value ? [Number(e.target.value)] : undefined)}
        >
          <option value="">All categories</option>
          {categories
            .filter((c) => c.parent_id)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {categoryPath(categories, c.id)}
              </option>
            ))}
        </Select>
        <Select
          value={(f.account_id as number[] | undefined)?.[0] ?? ""}
          onChange={(e) => set("account_id", e.target.value ? [Number(e.target.value)] : undefined)}
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select value={(f.direction as string) ?? ""} onChange={(e) => set("direction", e.target.value)}>
          <option value="">In & out</option>
          <option value="inflow">Inflows</option>
          <option value="outflow">Outflows</option>
        </Select>
        <Select value={(f.reconciliation as string) ?? ""} onChange={(e) => set("reconciliation", e.target.value)}>
          <option value="">Any reconciliation</option>
          <option value="linked">Linked</option>
          <option value="unlinked">Unlinked</option>
          <option value="duplicate">Duplicates</option>
        </Select>
        <Select
          value={f.max_confidence !== undefined ? String(f.max_confidence) : ""}
          onChange={(e) => set("max_confidence", e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">Any confidence</option>
          <option value="0.5">Low confidence</option>
          <option value="0.8">Below 80%</option>
        </Select>
        {(Object.values(f).some((v) => v !== undefined) || q) && (
          <Button variant="ghost" size="sm" onClick={() => { setF({}); setQ(""); }}>
            Clear
          </Button>
        )}
        <span className="ml-auto text-xs text-fg-muted">{res.data ? `${res.data.total.toLocaleString()} transactions` : ""}</span>
      </div>

      <ErrorNote error={res.error} />
      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-fg-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Date</th>
              <th className="px-3 py-2 font-medium">Description</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Account</th>
              <th className="px-3 py-2 text-right font-medium">Amount</th>
              <th className="px-3 py-2 font-medium">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {res.data?.items.map((t) => (
              <tr
                key={t.id}
                onClick={() => setSelected(t.id)}
                className={cn("cursor-pointer border-b border-border/60 last:border-0 hover:bg-muted/50", t.duplicate_of_id && "opacity-50")}
              >
                <td className="num whitespace-nowrap px-3 py-2 text-fg-muted">{date(t.txn_date)}</td>
                <td className="max-w-md px-3 py-2">
                  <p className="truncate font-medium">{t.merchant ?? t.description_raw}</p>
                  <p className="truncate text-xs text-fg-subtle">{t.description_raw}</p>
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    {categoryPath(categories, t.category_id)}
                    {t.pinned_fields.includes("category") && <Pin size={11} className="text-accent" />}
                    {t.is_recurring && <Repeat size={11} className="text-fg-subtle" />}
                  </span>
                  {t.role && <p className="text-[11px] text-fg-subtle">{ROLE_LABEL[t.role]}</p>}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-fg-muted">
                  {t.account}
                  {t.owner_identity_id && <p className="text-[11px] text-fg-subtle">{owner(t.owner_identity_id)}</p>}
                </td>
                <td className={cn("num whitespace-nowrap px-3 py-2 text-right font-medium", t.direction === "inflow" ? "text-positive" : "")}>
                  {money(t.amount, t.currency)}
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <Confidence value={t.classification_confidence} method={t.classification_method} />
                    <span className="text-[11px] text-fg-subtle">{humanize(t.classification_method)}</span>
                    {t.duplicate_of_id && <Badge tone="warning">duplicate</Badge>}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {res.data && res.data.total > PAGE && (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Previous
          </Button>
          <span className="text-xs text-fg-muted">
            {offset + 1}–{Math.min(offset + PAGE, res.data.total)} of {res.data.total}
          </span>
          <Button variant="outline" size="sm" disabled={offset + PAGE >= res.data.total} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </div>
      )}

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title="Transaction" wide>
        {selected !== null && <TransactionDetail id={selected} onChanged={() => void res.reload()} onOpen={setSelected} />}
      </Drawer>
    </div>
  );
}
