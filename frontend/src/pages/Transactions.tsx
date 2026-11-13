import { ChevronDown, ChevronUp, EyeOff, Pin, Repeat, Sigma } from "lucide-react";
import { useEffect, useState } from "react";
import { TransactionDetail } from "../components/TransactionDetail";
import { Badge, Button, Confidence, Drawer, ErrorNote, Input, Select, cn } from "../components/ui";
import { categoryPath, useApp } from "../lib/context";
import { date, humanize, money } from "../lib/format";
import { useApi } from "../lib/hooks";
import { ROLES, ROLE_LABEL, type DocumentInfo, type SourceTotals, type Txn, type TxnTotals } from "../lib/types";

type Filter = Record<string, string | number | (string | number)[] | undefined>;

const PAGE = 100;
const TOTALS_KEY = "ledger.txn.totals";

function readPref(): "shown" | "hidden" | "expanded" {
  try {
    const v = localStorage.getItem(TOTALS_KEY);
    return v === "hidden" || v === "expanded" ? v : "shown";
  } catch {
    return "shown";
  }
}

export default function TransactionsPage({ initialFilter }: { initialFilter?: Filter }) {
  const { filters, accounts, categories, identities } = useApp();
  const [f, setF] = useState<Filter>(initialFilter ?? {});
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => setF(initialFilter ?? {}), [initialFilter]);
  useEffect(() => setOffset(0), [f, q, filters]);

  const query = { ...filters, ...f, q, limit: PAGE, offset };
  const res = useApi<{ total: number; items: Txn[]; totals: TxnTotals[]; by_source: SourceTotals[] }>("/transactions", query);
  const docs = useApi<DocumentInfo[]>("/documents");
  const [totalsPref, setTotalsPrefState] = useState(readPref);
  const setTotalsPref = (v: "shown" | "hidden" | "expanded") => {
    setTotalsPrefState(v);
    try {
      localStorage.setItem(TOTALS_KEY, v);
    } catch {
      /* preference only */
    }
  };
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
        <Select
          value={(f.document_id as number[] | undefined)?.[0] ?? ""}
          onChange={(e) => set("document_id", e.target.value ? [Number(e.target.value)] : undefined)}
        >
          <option value="">All statements</option>
          {(docs.data ?? [])
            .filter((d) => d.status === "processed")
            .map((d) => (
              <option key={d.id} value={d.id}>
                {d.original_filename}
                {d.statement_end ? ` · ${date(d.statement_start)} – ${date(d.statement_end)}` : ""}
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
        {totalsPref === "hidden" && (
          <Button variant="ghost" size="sm" onClick={() => setTotalsPref("shown")} title="Show totals">
            <Sigma size={13} /> Totals
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

      {res.data && res.data.total > 0 && totalsPref !== "hidden" && (
        <TotalsBar
          totals={res.data.totals}
          bySource={res.data.by_source}
          expanded={totalsPref === "expanded"}
          onToggle={() => setTotalsPref(totalsPref === "expanded" ? "shown" : "expanded")}
          onHide={() => setTotalsPref("hidden")}
          onPickSource={(id) => set("document_id", id === null ? undefined : [id])}
          activeSource={(f.document_id as number[] | undefined)?.[0] ?? null}
        />
      )}

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title="Transaction" wide>
        {selected !== null && <TransactionDetail id={selected} onChanged={() => void res.reload()} onOpen={setSelected} />}
      </Drawer>
    </div>
  );
}

/** Spreadsheet-style status bar: sums of every transaction matching the filters (not just
 *  this page), optionally broken down by the statement each one came from. */
function TotalsBar({
  totals,
  bySource,
  expanded,
  onToggle,
  onHide,
  onPickSource,
  activeSource,
}: {
  totals: TxnTotals[];
  bySource: SourceTotals[];
  expanded: boolean;
  onToggle: () => void;
  onHide: () => void;
  onPickSource: (id: number | null) => void;
  activeSource: number | null;
}) {
  return (
    <div className="sticky bottom-0 z-10 -mx-1 rounded-lg border border-border bg-surface/95 px-3 py-2 text-xs shadow-sm backdrop-blur">
      {expanded && (
        <div className="mb-2 max-h-64 overflow-y-auto border-b border-border pb-2">
          <table className="w-full">
            <thead className="text-left text-fg-muted">
              <tr>
                <th className="py-1 pr-3 font-medium">Statement</th>
                <th className="py-1 pr-3 font-medium">Period</th>
                <th className="py-1 pr-3 text-right font-medium">Rows</th>
                <th className="py-1 pr-3 text-right font-medium">Money in</th>
                <th className="py-1 text-right font-medium">Money out</th>
              </tr>
            </thead>
            <tbody>
              {bySource.map((r) => (
                <tr
                  key={`${r.document_id}-${r.currency}`}
                  onClick={() => r.document_id !== null && onPickSource(activeSource === r.document_id ? null : r.document_id)}
                  className={cn("border-t border-border/60", r.document_id !== null && "cursor-pointer hover:bg-muted/50", activeSource === r.document_id && "bg-accent/5")}
                  title={r.document_id !== null ? (activeSource === r.document_id ? "Clear statement filter" : "Show only this statement") : undefined}
                >
                  <td className="py-1 pr-3 font-medium">{r.name}</td>
                  <td className="num py-1 pr-3 text-fg-muted">{r.statement_end ? `${date(r.statement_start)} – ${date(r.statement_end)}` : "—"}</td>
                  <td className="num py-1 pr-3 text-right">{r.count}</td>
                  <td className="num py-1 pr-3 text-right text-positive">{money(r.inflow, r.currency)}</td>
                  <td className="num py-1 text-right">{money(Math.abs(Number(r.outflow)), r.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        {totals.map((t) => (
          <span key={t.currency} className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="text-fg-muted">
              <Sigma size={12} className="mr-1 inline" />
              {t.count.toLocaleString()} {totals.length > 1 ? t.currency : "transactions"}
            </span>
            <span>
              <span className="text-fg-muted">In </span>
              <span className="num font-medium text-positive">{money(t.inflow, t.currency)}</span>
            </span>
            <span>
              <span className="text-fg-muted">Out </span>
              <span className="num font-medium">{money(Math.abs(Number(t.outflow)), t.currency)}</span>
            </span>
            <span>
              <span className="text-fg-muted">Net </span>
              <span className={cn("num font-medium", Number(t.net) < 0 ? "text-negative" : "text-positive")}>{money(t.net, t.currency)}</span>
            </span>
          </span>
        ))}
        <span className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={onToggle}>
            {expanded ? <ChevronDown size={13} /> : <ChevronUp size={13} />} By statement ({bySource.length})
          </Button>
          <Button variant="ghost" size="sm" onClick={onHide} aria-label="Hide totals" title="Hide totals">
            <EyeOff size={13} />
          </Button>
        </span>
      </div>
    </div>
  );
}
