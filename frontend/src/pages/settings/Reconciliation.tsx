import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button, Card, Field, Input } from "../../components/ui";
import { api } from "../../lib/api";
import { useApp } from "../../lib/context";
import type { ReconciliationSettings } from "../../lib/types";

/** Matching rules only; reviewing the matches themselves lives on the Reconciliation page. */
export default function Reconciliation() {
  const { settings, refresh } = useApp();
  const [r, setR] = useState<ReconciliationSettings | null>(settings?.reconciliation ?? null);
  useEffect(() => setR(settings?.reconciliation ?? null), [settings]);
  if (!r) return null;

  const save = async () => {
    try {
      await api.put("/settings/reconciliation", r);
      await api.post("/reconciliation/run");
      await refresh();
      toast.success("Saved", { description: "Matching is re-running in the background. Matches you confirmed or rejected are kept." });
    } catch (e) {
      toast.error("Could not save", { description: (e as Error).message });
    }
  };

  return (
    <Card title="Matching windows">
      <p className="mb-3 text-xs text-fg-muted">
        How far apart two transactions may be and still be paired. Review the resulting matches on the Reconciliation page.
      </p>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Transfers (days)" help="transfer_window">
          <Input type="number" value={r.transfer_window_days} onChange={(e) => setR({ ...r, transfer_window_days: Number(e.target.value) })} />
        </Field>
        <Field label="Card payments (days)" help="settlement_window">
          <Input type="number" value={r.settlement_window_days} onChange={(e) => setR({ ...r, settlement_window_days: Number(e.target.value) })} />
        </Field>
        <Field label="Refunds (days)" help="refund_window">
          <Input type="number" value={r.refund_window_days} onChange={(e) => setR({ ...r, refund_window_days: Number(e.target.value) })} />
        </Field>
        <Field label="Duplicate threshold" help="duplicate_threshold">
          <Input type="number" step="0.05" min="0.5" max="1" value={r.duplicate_min_confidence} onChange={(e) => setR({ ...r, duplicate_min_confidence: Number(e.target.value) })} />
        </Field>
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={save}>Save & re-run</Button>
      </div>
    </Card>
  );
}
