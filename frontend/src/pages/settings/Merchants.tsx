import { Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Drawer, ErrorNote, Field, Input, Select } from "../../components/ui";
import { api } from "../../lib/api";
import { categoryPath, useApp } from "../../lib/context";
import { useApi } from "../../lib/hooks";
import type { Merchant } from "../../lib/types";

export default function Merchants() {
  const { categories } = useApp();
  const [q, setQ] = useState("");
  const list = useApi<{ total: number; items: Merchant[] }>("/merchants", { q, limit: 200 });
  const [sel, setSel] = useState<Merchant | null>(null);
  const [name, setName] = useState("");
  const [alias, setAlias] = useState("");
  const [mergeTarget, setMergeTarget] = useState<number | "">("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = (m: Merchant) => {
    setSel(m);
    setName(m.canonical_name);
    setAlias("");
    setMsg(null);
    setError(null);
  };
  const run = async (fn: () => Promise<string | void>) => {
    setError(null);
    try {
      const m = await fn();
      if (m) setMsg(m);
      await list.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const refreshSel = async (id: number) => {
    const r = await api.get<{ items: Merchant[] }>("/merchants", { limit: 1000 });
    setSel(r.items.find((x) => x.id === id) ?? null);
  };

  return (
    <Card title={`Merchants${list.data ? ` (${list.data.total})` : ""}`}>
      <p className="mb-3 text-sm text-fg-muted">
        Merchants group messy statement descriptions into one counterparty. Mapping a merchant to a category re-classifies its history
        and future imports (your pinned corrections are kept).
      </p>
      <Input className="mb-3 max-w-sm" placeholder="Search merchants" value={q} onChange={(e) => setQ(e.target.value)} />
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-fg-muted">
          <tr>
            <th className="pb-2 font-medium">Merchant</th>
            <th className="pb-2 font-medium">Default category</th>
            <th className="pb-2 font-medium">Source</th>
            <th className="pb-2 text-right font-medium">Transactions</th>
          </tr>
        </thead>
        <tbody>
          {(list.data?.items ?? []).map((m) => (
            <tr key={m.id} className="cursor-pointer border-t border-border/60 hover:bg-muted/50" onClick={() => open(m)}>
              <td className="py-1.5">{m.canonical_name}</td>
              <td className="py-1.5 text-fg-muted">{m.default_category_id ? categoryPath(categories, m.default_category_id) : "—"}</td>
              <td className="py-1.5">
                <Badge tone={m.source === "user" ? "accent" : "neutral"}>{m.source}</Badge>
              </td>
              <td className="num py-1.5 text-right">{m.transaction_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <Drawer open={!!sel} onClose={() => setSel(null)} title={sel?.canonical_name ?? ""}>
        {sel && (
          <div className="space-y-5">
            {msg && <p className="rounded-md bg-accent/10 px-3 py-2 text-sm text-accent">{msg}</p>}
            <ErrorNote error={error} />
            <div className="flex items-end gap-2">
              <Field label="Canonical name">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Button variant="outline" onClick={() => run(async () => { await api.patch(`/merchants/${sel.id}`, { canonical_name: name }); return "Renamed"; })}>
                Rename
              </Button>
            </div>
            <Field label="Default category" hint="Applies to all non-pinned transactions from this merchant.">
              <Select
                className="w-full"
                value={sel.default_category_id ?? ""}
                onChange={(e) =>
                  run(async () => {
                    const r = await api.patch<{ reclassified: number; merchant: Merchant }>(`/merchants/${sel.id}`, {
                      default_category_id: e.target.value ? Number(e.target.value) : null,
                    });
                    setSel(r.merchant);
                    return `Mapped; ${r.reclassified} transactions re-classified.`;
                  })
                }
              >
                <option value="">None (classify automatically)</option>
                {categories
                  .filter((c) => c.parent_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {categoryPath(categories, c.id)}
                    </option>
                  ))}
              </Select>
            </Field>
            <div>
              <p className="mb-1 text-xs font-medium text-fg-muted">Matching patterns</p>
              <ul className="space-y-1">
                {sel.aliases.map((a) => (
                  <li key={a.id} className="flex items-center gap-2 text-sm">
                    <Badge>{a.match_type}</Badge>
                    <code className="text-xs">{a.pattern}</code>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto"
                      onClick={() => run(async () => { await api.del(`/merchants/${sel.id}/aliases/${a.id}`); await refreshSel(sel.id); })}
                    >
                      <Trash2 size={12} />
                    </Button>
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex gap-2">
                <Input placeholder="Text that appears in descriptions, e.g. instamart" value={alias} onChange={(e) => setAlias(e.target.value)} />
                <Button
                  variant="outline"
                  disabled={!alias.trim()}
                  onClick={() =>
                    run(async () => {
                      await api.post(`/merchants/${sel.id}/aliases`, { pattern: alias, match_type: "contains" });
                      await refreshSel(sel.id);
                      setAlias("");
                      return "Pattern added; matching transactions are being re-mapped.";
                    })
                  }
                >
                  Add
                </Button>
              </div>
            </div>
            <div className="flex items-end gap-2">
              <Field label="Merge into another merchant">
                <Select className="w-full" value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">Choose…</option>
                  {(list.data?.items ?? [])
                    .filter((m) => m.id !== sel.id)
                    .map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.canonical_name}
                      </option>
                    ))}
                </Select>
              </Field>
              <Button
                variant="outline"
                disabled={!mergeTarget}
                onClick={() =>
                  run(async () => {
                    await api.post(`/merchants/${sel.id}/merge-into/${mergeTarget}`);
                    setSel(null);
                  })
                }
              >
                Merge
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </Card>
  );
}
