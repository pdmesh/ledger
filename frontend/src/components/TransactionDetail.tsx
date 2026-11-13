import { ExternalLink, Pin } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api, openDocument } from "../lib/api";
import { categoryPath, useApp } from "../lib/context";
import { date, humanize, money } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { Merchant, TxnDetail } from "../lib/types";
import { Badge, Button, Card, Confidence, ErrorNote, Select, Toggle, confirmAction } from "./ui";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

const LINK_LABEL: Record<string, string> = {
  internal_transfer: "Internal transfer",
  card_settlement: "Card settlement",
  refund: "Refund",
  duplicate: "Duplicate",
};

export function TransactionDetail({
  id,
  onChanged,
  onOpen,
  onDeleted,
}: {
  id: number;
  onChanged: () => void;
  onOpen: (id: number) => void;
  onDeleted?: () => void;
}) {
  const { categories, identities, accounts } = useApp();
  const d = useApi<TxnDetail>(`/transactions/${id}`);
  const merchants = useApi<{ items: Merchant[] }>("/merchants", { limit: 500 });
  const [learn, setLearn] = useState(true);
  const [error, setError] = useState<string | null>(null);

  if (!d.data) return <ErrorNote error={d.error} />;
  const t = d.data;

  const override = async (field: string, value: unknown, applyToSimilar = false) => {
    setError(null);
    try {
      await api.post(`/transactions/${t.id}/override`, { field, value, apply_to_similar: applyToSimilar });
      await d.reload();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const unpin = async (field: string) => {
    await api.del(`/transactions/${t.id}/override/${field}`);
    await d.reload();
    onChanged();
  };
  const setLink = async (linkId: number, status: string) => {
    await api.post(`/reconciliation/links/${linkId}`, { status });
    await d.reload();
    onChanged();
  };
  const removeManual = async () => {
    const ok = await confirmAction({
      title: "Delete this transaction?",
      body: "It was entered by hand, so deleting it removes it for good.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/transactions/${t.id}`);
      toast.success("Transaction deleted");
      onChanged();
      onDeleted?.();
    } catch (e) {
      toast.error("Could not delete", { description: (e as Error).message });
    }
  };
  const openDoc = async () => {
    if (!t.document) return;
    try {
      await openDocument(t.document.id);
    } catch (e) {
      toast.error("Could not open the statement", { description: (e as Error).message });
    }
  };
  const pinned = (f: string) =>
    t.pinned_fields.includes(f) ? (
      <button className="ml-1 inline-flex items-center gap-1 text-[11px] text-accent hover:underline" onClick={() => unpin(f)} title="Release to automatic classification">
        <Pin size={11} /> pinned · unpin
      </button>
    ) : null;

  return (
    <div className="space-y-5">
      <div>
        <p className={`num text-2xl font-semibold ${t.direction === "inflow" ? "text-positive" : ""}`}>{money(t.amount, t.currency)}</p>
        {t.base_amount && t.base_amount !== t.amount && <p className="num text-sm text-fg-muted">{money(t.base_amount)} in base currency</p>}
        <p className="mt-1 text-sm text-fg-muted">
          {date(t.txn_date)} · {t.account}
        </p>
      </div>
      <ErrorNote error={error} />

      <Card title="Classification">
        <dl>
          <Row label="Category">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={t.category_id ?? ""} onChange={(e) => override("category", Number(e.target.value), learn)} className="max-w-xs">
                {t.category_id === null && <option value="">Uncategorized</option>}
                {categories
                  .filter((c) => c.parent_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {categoryPath(categories, c.id)}
                    </option>
                  ))}
              </Select>
              {pinned("category")}
            </div>
            <div className="mt-2">
              <Toggle checked={learn} onChange={setLearn} label={<span className="text-xs text-fg-muted">Apply to this merchant's other and future transactions</span>} />
            </div>
          </Row>
          <Row label="Merchant">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={t.merchant_id ?? ""} onChange={(e) => override("merchant", e.target.value ? Number(e.target.value) : null)} className="max-w-xs">
                <option value="">None</option>
                {(merchants.data?.items ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.canonical_name}
                  </option>
                ))}
              </Select>
              {pinned("merchant")}
            </div>
          </Row>
          <Row label="Attributed to">
            <div className="flex items-center gap-2">
              <Select value={t.owner_identity_id ?? ""} onChange={(e) => override("owner", e.target.value ? Number(e.target.value) : null)}>
                <option value="">Account owners</option>
                {identities.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.display_name}
                  </option>
                ))}
              </Select>
              {pinned("owner")}
            </div>
          </Row>
          <Row label="Account">
            <div className="flex items-center gap-2">
              <Select value={t.account_id} onChange={(e) => override("account", Number(e.target.value))}>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
              {pinned("account")}
            </div>
          </Row>
          <Row label="Direction">
            <div className="flex items-center gap-2">
              <Select value={t.direction} onChange={(e) => override("direction", e.target.value)}>
                <option value="inflow">Inflow</option>
                <option value="outflow">Outflow</option>
              </Select>
              {pinned("direction")}
            </div>
          </Row>
          <Row label="Decided by">
            <span className="flex items-center gap-2">
              <Confidence value={t.classification_confidence} method={t.classification_method} />
              {humanize(t.classification_method)}
              {t.classification_config_version !== null && <span className="text-xs text-fg-subtle">config v{t.classification_config_version}</span>}
            </span>
            {Object.keys(t.classification_evidence ?? {}).length > 0 && (
              <pre className="mt-1.5 overflow-x-auto rounded bg-muted px-2 py-1.5 text-[11px] text-fg-muted">{JSON.stringify(t.classification_evidence, null, 2)}</pre>
            )}
          </Row>
        </dl>
      </Card>

      <Card title="Reconciliation">
        {t.links.length === 0 && <p className="text-sm text-fg-muted">Not linked to other transactions.</p>}
        <ul className="space-y-3">
          {t.links.map((lk) => (
            <li key={lk.id} className="rounded-md border border-border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={lk.status === "rejected" ? "negative" : "accent"}>{LINK_LABEL[lk.kind]}</Badge>
                <Badge>{Math.round(lk.confidence * 100)}%</Badge>
                <span className="text-xs text-fg-muted">
                  {lk.method} · {lk.status}
                </span>
                <span className="ml-auto flex gap-1">
                  {lk.status !== "confirmed" && (
                    <Button size="sm" variant="outline" onClick={() => setLink(lk.id, "confirmed")}>
                      Confirm
                    </Button>
                  )}
                  {lk.status !== "rejected" && (
                    <Button size="sm" variant="outline" onClick={() => setLink(lk.id, "rejected")}>
                      Not related
                    </Button>
                  )}
                </span>
              </div>
              {lk.counterpart && (
                <button className="mt-2 block w-full text-left hover:underline" onClick={() => onOpen(lk.counterpart!.id)}>
                  {date(lk.counterpart.txn_date)} · {lk.counterpart.account} · {lk.counterpart.description_raw} ·{" "}
                  <span className="num">{money(lk.counterpart.amount, lk.counterpart.currency)}</span>
                </button>
              )}
              <pre className="mt-1.5 overflow-x-auto rounded bg-muted px-2 py-1.5 text-[11px] text-fg-muted">{JSON.stringify(lk.evidence, null, 2)}</pre>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Source">
        <dl>
          <Row label="Original description">
            <code className="text-xs">{t.description_raw}</code>
          </Row>
          {t.reference && <Row label="Reference">{t.reference}</Row>}
          {t.balance_after && <Row label="Balance after">{money(t.balance_after, t.currency)}</Row>}
          <Row label="Document">
            {t.document ? (
              <button className="inline-flex items-center gap-1 hover:underline" onClick={openDoc}>
                {t.document.filename} <ExternalLink size={12} />
              </button>
            ) : t.entry_method === "manual" ? (
              <span className="inline-flex items-center gap-2">
                Entered by hand
                <Button size="sm" variant="ghost" onClick={removeManual}>
                  Delete
                </Button>
              </span>
            ) : (
              humanize(t.entry_method)
            )}
          </Row>
          <Row label="Location">
            <code className="text-xs">{JSON.stringify(t.source_ref)}</code>
          </Row>
          <Row label="Extracted values">
            <pre className="overflow-x-auto rounded bg-muted px-2 py-1.5 text-[11px] text-fg-muted">{JSON.stringify(t.raw, null, 2)}</pre>
          </Row>
        </dl>
      </Card>

      <Card title="History">
        <ol className="space-y-2 text-sm">
          {t.history.map((h, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs text-fg-subtle">{new Date(h.at).toLocaleString()}</span>
              <Badge>{h.method}</Badge>
              <span>{h.category ?? "—"}</span>
              {h.model && <span className="text-xs text-fg-subtle">via {h.provider} / {h.model}</span>}
              {h.confidence !== null && <span className="text-xs text-fg-subtle">{Math.round(h.confidence * 100)}%</span>}
            </li>
          ))}
          {t.overrides.map((o, i) => (
            <li key={`o${i}`} className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs text-fg-subtle">{new Date(o.at).toLocaleString()}</span>
              <Badge tone="accent">you</Badge>
              <span>
                changed {o.field}
                {o.apply_to_similar ? " (applied to similar)" : ""}
              </span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
