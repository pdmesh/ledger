import { useEffect, useState } from "react";
import { Badge, Button, Card, Field, Input, Select } from "../../components/ui";
import { api } from "../../lib/api";
import { useApp } from "../../lib/context";
import { date, humanize, money } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import type { Link, ReconciliationSettings } from "../../lib/types";

export default function Reconciliation() {
  const { settings, refresh } = useApp();
  const [r, setR] = useState<ReconciliationSettings | null>(settings?.reconciliation ?? null);
  const [kind, setKind] = useState("");
  const links = useApi<Link[]>("/reconciliation/links", { kind, limit: 200 });
  useEffect(() => setR(settings?.reconciliation ?? null), [settings]);
  if (!r) return null;

  const save = async () => {
    await api.put("/settings/reconciliation", r);
    await api.post("/reconciliation/run");
    await refresh();
  };
  const setStatus = async (id: number, status: string) => {
    await api.post(`/reconciliation/links/${id}`, { status });
    await links.reload();
  };

  return (
    <div className="space-y-5">
      <Card title="Matching windows">
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Transfers (days)">
            <Input type="number" value={r.transfer_window_days} onChange={(e) => setR({ ...r, transfer_window_days: Number(e.target.value) })} />
          </Field>
          <Field label="Card settlements (days)">
            <Input type="number" value={r.settlement_window_days} onChange={(e) => setR({ ...r, settlement_window_days: Number(e.target.value) })} />
          </Field>
          <Field label="Refunds (days)">
            <Input type="number" value={r.refund_window_days} onChange={(e) => setR({ ...r, refund_window_days: Number(e.target.value) })} />
          </Field>
          <Field label="Duplicate threshold" hint="Minimum confidence to hide a duplicate.">
            <Input type="number" step="0.05" min="0.5" max="1" value={r.duplicate_min_confidence} onChange={(e) => setR({ ...r, duplicate_min_confidence: Number(e.target.value) })} />
          </Field>
        </div>
        <div className="mt-4 flex justify-end">
          <Button onClick={save}>Save & re-run</Button>
        </div>
      </Card>

      <Card
        title="Relationships"
        actions={
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All kinds</option>
            <option value="internal_transfer">Internal transfers</option>
            <option value="card_settlement">Card settlements</option>
            <option value="refund">Refunds</option>
            <option value="duplicate">Duplicates</option>
          </Select>
        }
      >
        <p className="mb-3 text-xs text-fg-muted">Linked transactions are never deleted. Rejecting a link restores independent classification and is remembered.</p>
        <table className="w-full text-sm">
          <tbody>
            {(links.data ?? []).map((lk) => (
              <tr key={lk.id} className="border-t border-border/60 align-top">
                <td className="py-2 pr-3">
                  <Badge tone={lk.status === "rejected" ? "negative" : lk.status === "confirmed" ? "positive" : "accent"}>{humanize(lk.kind)}</Badge>
                  <p className="mt-1 text-[11px] text-fg-subtle">
                    {Math.round(lk.confidence * 100)}% · {lk.method} · {lk.status}
                  </p>
                </td>
                {[lk.from, lk.to].map((t, i) => (
                  <td key={i} className="py-2 pr-3 text-xs">
                    {t && (
                      <>
                        <p className="font-medium">{t.account}</p>
                        <p className="text-fg-muted">
                          {date(t.txn_date)} · <span className="num">{money(t.amount, t.currency)}</span>
                        </p>
                        <p className="truncate text-fg-subtle">{t.description_raw}</p>
                      </>
                    )}
                  </td>
                ))}
                <td className="whitespace-nowrap py-2 text-right">
                  {lk.status !== "confirmed" && (
                    <Button size="sm" variant="ghost" onClick={() => setStatus(lk.id, "confirmed")}>
                      Confirm
                    </Button>
                  )}
                  {lk.status !== "rejected" && (
                    <Button size="sm" variant="ghost" onClick={() => setStatus(lk.id, "rejected")}>
                      Reject
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
