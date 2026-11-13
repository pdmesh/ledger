import { ArrowRight, Check, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { TransactionDetail } from "../components/TransactionDetail";
import { Badge, Button, Drawer, Empty, ErrorNote, Help, Select, Tabs, Term, cn } from "../components/ui";
import { api } from "../lib/api";
import { date, humanize, money } from "../lib/format";
import { GLOSSARY, type GlossaryKey } from "../lib/glossary";
import { useApi } from "../lib/hooks";
import type { Link, Txn } from "../lib/types";

type View = "auto" | "confirmed" | "rejected" | "";

export interface LinkSummary {
  to_review: number;
  by_status: Record<string, Record<string, number>>;
}

const KINDS: Link["kind"][] = ["card_settlement", "internal_transfer", "refund", "duplicate"];
const KIND_LABEL: Record<Link["kind"], string> = {
  internal_transfer: "Transfer",
  card_settlement: "Card payment",
  refund: "Refund",
  duplicate: "Duplicate",
};
// which side of the link is which, in plain words
const SIDES: Record<Link["kind"], [string, string]> = {
  internal_transfer: ["From", "To"],
  card_settlement: ["Bank payment", "Card"],
  refund: ["Purchase", "Refund"],
  duplicate: ["Original", "Copy (hidden)"],
};
const STATUS_TERM: Record<Link["status"], GlossaryKey> = { auto: "link_auto", confirmed: "link_confirmed", rejected: "link_rejected" };
const STATUS_LABEL: Record<Link["status"], string> = { auto: "Needs review", confirmed: "Confirmed", rejected: "Rejected" };

const methodTerm = (m: string): GlossaryKey | undefined => (`method_${m}` in GLOSSARY ? (`method_${m}` as GlossaryKey) : undefined);

/** Tell the navigation badge that review counts changed. */
export const RECON_CHANGED = "ledger:reconciliation-changed";

export default function ReconciliationPage() {
  const [view, setView] = useState<View>("auto");
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const summary = useApi<LinkSummary>("/reconciliation/summary");
  const links = useApi<Link[]>("/reconciliation/links", {
    status: view || undefined,
    kind: kind || undefined,
    sort: view === "auto" ? "confidence" : "recent",
    limit: 300,
  });

  const count = (status: string) => Object.values(summary.data?.by_status[status] ?? {}).reduce((a, b) => a + b, 0);
  const kindCount = (k: string) =>
    view ? (summary.data?.by_status[view]?.[k] ?? 0) : Object.values(summary.data?.by_status ?? {}).reduce((a, s) => a + (s[k] ?? 0), 0);

  const setStatus = async (lk: Link, status: "confirmed" | "rejected") => {
    try {
      await api.post(`/reconciliation/links/${lk.id}`, { status });
      // drop it from the review queue right away; the reload catches up
      if (view === "auto") links.setData((links.data ?? []).filter((x) => x.id !== lk.id));
      toast.success(status === "confirmed" ? `${KIND_LABEL[lk.kind]} confirmed` : `${KIND_LABEL[lk.kind]} rejected`, {
        description: status === "rejected" ? "Both transactions will be classified on their own again." : undefined,
      });
      await Promise.all([links.reload(), summary.reload()]);
      window.dispatchEvent(new Event(RECON_CHANGED));
    } catch (e) {
      toast.error("Could not update the match", { description: (e as Error).message });
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Reconciliation</h1>
        <p className="mt-1 max-w-3xl text-sm text-fg-muted">
          The ledger pairs up transactions that are two sides of the same money: transfers between your accounts, card bill payments, refunds and
          duplicate imports. That way nothing is counted twice. Matches are already in effect; confirm the ones that are right and reject the
          ones that aren&apos;t. Nothing here deletes a transaction.
        </p>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <Tabs
          value={view}
          onChange={setView}
          items={[
            { value: "auto", label: `Needs review (${count("auto")})` },
            { value: "confirmed", label: `Confirmed (${count("confirmed")})` },
            { value: "rejected", label: `Rejected (${count("rejected")})` },
            { value: "", label: "All" },
          ]}
        />
        <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind of match">
          <option value="">All kinds</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]} ({kindCount(k)})
            </option>
          ))}
        </Select>
      </div>

      <ErrorNote error={links.error ?? summary.error} />

      {links.data && links.data.length === 0 ? (
        <Empty title={view === "auto" ? "Nothing to review" : "No matches here"}>
          {view === "auto" ? "Every automatic match has been confirmed or rejected." : "Try another tab or kind."}
        </Empty>
      ) : (
        <ul className="space-y-2">
          {(links.data ?? []).map((lk) => (
            <li key={lk.id} className="rounded-lg border border-border bg-surface p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <Term term={lk.kind}>
                  <Badge tone="accent">{KIND_LABEL[lk.kind]}</Badge>
                </Term>
                <Term term="match_confidence" className="text-fg-muted">
                  {Math.round(lk.confidence * 100)}% match
                </Term>
                <span className="text-fg-subtle">·</span>
                <Term term={methodTerm(lk.method)} className="text-fg-muted">
                  {lk.method === "llm" ? "AI-assisted" : humanize(lk.method)}
                </Term>
                <span className="text-fg-subtle">·</span>
                <Term term={STATUS_TERM[lk.status]}>
                  <Badge tone={lk.status === "rejected" ? "negative" : lk.status === "confirmed" ? "positive" : "warning"}>{STATUS_LABEL[lk.status]}</Badge>
                </Term>
                <span className="ml-auto flex gap-1.5">
                  {lk.status !== "confirmed" && (
                    <Button size="sm" variant="outline" onClick={() => setStatus(lk, "confirmed")}>
                      <Check size={13} /> Confirm
                    </Button>
                  )}
                  {lk.status !== "rejected" && (
                    <Button size="sm" variant="ghost" onClick={() => setStatus(lk, "rejected")}>
                      <X size={13} /> Reject
                    </Button>
                  )}
                </span>
              </div>
              <div className="grid items-stretch gap-2 sm:grid-cols-[1fr_auto_1fr]">
                <Side label={SIDES[lk.kind][0]} t={lk.from} onOpen={setOpen} />
                <ArrowRight size={14} className="hidden self-center text-fg-subtle sm:block" />
                <Side label={SIDES[lk.kind][1]} t={lk.to} onOpen={setOpen} />
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="flex items-center gap-1 text-xs text-fg-muted">
        Matching windows and the duplicate threshold are in Settings → Reconciliation rules. <Help term="transfer_window" />
      </p>

      <Drawer open={open !== null} onClose={() => setOpen(null)} title="Transaction" wide>
        {open !== null && <TransactionDetail id={open} onChanged={() => void links.reload()} onOpen={setOpen} />}
      </Drawer>
    </div>
  );
}

function Side({ label, t, onOpen }: { label: string; t: Txn | null | undefined; onOpen: (id: number) => void }) {
  if (!t) return <div className="rounded-md bg-muted/50 px-3 py-2 text-xs text-fg-subtle">{label}: transaction no longer exists</div>;
  return (
    <button
      onClick={() => onOpen(t.id)}
      className="rounded-md bg-muted/40 px-3 py-2 text-left text-xs hover:bg-muted"
      title="Open transaction"
    >
      <p className="mb-0.5 text-[11px] uppercase tracking-wide text-fg-subtle">{label}</p>
      <p className="flex items-baseline justify-between gap-2">
        <span className="truncate font-medium">{t.account}</span>
        <span className={cn("num shrink-0 font-medium", t.direction === "inflow" && "text-positive")}>{money(t.amount, t.currency)}</span>
      </p>
      <p className="mt-0.5 flex justify-between gap-2 text-fg-muted">
        <span className="truncate">{t.merchant ?? t.description_raw}</span>
        <span className="num shrink-0">{date(t.txn_date)}</span>
      </p>
    </button>
  );
}
