import { Pencil, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import type { NavTarget } from "../App";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, Select } from "../components/ui";
import { api } from "../lib/api";
import { useApp } from "../lib/context";
import { date, humanize, money } from "../lib/format";
import { ACCOUNT_TYPES, type Account, type Institution } from "../lib/types";

interface Draft {
  id?: number;
  name: string;
  account_type: string;
  institution_id: number | null;
  masked_number: string;
  currency: string;
  owner_ids: number[];
  active: boolean;
}

export default function AccountsPage({ go }: { go: (t: NavTarget) => void }) {
  const { accounts, identities, settings, refresh } = useApp();
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
    api.get<Institution[]>("/institutions").then(setInstitutions);
  }, [refresh]);

  const open = (a?: Account) =>
    setDraft(
      a
        ? { id: a.id, name: a.name, account_type: a.account_type, institution_id: a.institution_id, masked_number: a.masked_number ?? "", currency: a.currency, owner_ids: a.owners.map((o) => o.identity_id), active: a.active }
        : { name: "", account_type: "savings", institution_id: null, masked_number: "", currency: settings?.general.base_currency ?? "", owner_ids: [], active: true },
    );

  const save = async () => {
    if (!draft) return;
    setError(null);
    try {
      const body = { ...draft, masked_number: draft.masked_number || null, aliases: [] };
      if (draft.id) await api.put(`/accounts/${draft.id}`, body);
      else await api.post("/accounts", body);
      setDraft(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const name = (id: number) => identities.find((i) => i.id === id)?.display_name ?? `#${id}`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-fg-muted">Accounts are discovered automatically from statements. Add or correct them here.</p>
        <Button size="sm" onClick={() => open()}>
          <Plus size={14} /> Add account
        </Button>
      </div>
      {accounts.length === 0 && <Empty title="No accounts yet">Import a statement and its account will appear here.</Empty>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {accounts.map((a) => (
          <Card
            key={a.id}
            title={
              <span className="flex items-center gap-2">
                {a.name}
                {!a.active && <Badge>inactive</Badge>}
              </span>
            }
            actions={
              <Button variant="ghost" size="sm" onClick={() => open(a)} aria-label="Edit">
                <Pencil size={13} />
              </Button>
            }
          >
            <div className="space-y-1.5 text-sm">
              <p className="text-fg-muted">
                {humanize(a.account_type)} · {a.institution ?? "Unknown institution"}
                {a.masked_number && ` · ••${a.masked_number}`} · {a.currency}
              </p>
              <p>
                {a.owners.length === 0 && <Badge tone="warning">owner unknown</Badge>}
                {a.owners.map((o) => (
                  <Badge key={o.identity_id} tone={o.source === "user" ? "accent" : "neutral"} className="mr-1">
                    {name(o.identity_id)}
                    {o.source !== "user" && ` · ${Math.round(o.confidence * 100)}%`}
                  </Badge>
                ))}
                {a.owners.length > 1 && <Badge tone="accent">joint</Badge>}
              </p>
              {a.last_balance && (
                <p className="num">
                  Last balance {money(a.last_balance, a.currency)}
                </p>
              )}
              <button className="text-xs text-fg-muted hover:underline" onClick={() => go({ section: "transactions", txnFilter: { account_id: [a.id] } })}>
                {a.transaction_count ?? 0} transactions · latest {date(a.last_transaction)}
              </button>
              {a.auto_discovered && <p className="text-[11px] text-fg-subtle">Discovered from a statement</p>}
            </div>
          </Card>
        ))}
      </div>

      <Modal open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? "Edit account" : "Add account"}>
        {draft && (
          <div className="space-y-3">
            <Field label="Name">
              <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type">
                <Select className="w-full" value={draft.account_type} onChange={(e) => setDraft({ ...draft, account_type: e.target.value })}>
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {humanize(t)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Institution">
                <Select className="w-full" value={draft.institution_id ?? ""} onChange={(e) => setDraft({ ...draft, institution_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>
                  {institutions.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Last 4 digits" hint="Only the last four digits are stored.">
                <Input value={draft.masked_number} maxLength={4} onChange={(e) => setDraft({ ...draft, masked_number: e.target.value.replace(/\D/g, "") })} />
              </Field>
              <Field label="Currency">
                <Input value={draft.currency} maxLength={3} onChange={(e) => setDraft({ ...draft, currency: e.target.value.toUpperCase() })} />
              </Field>
            </div>
            <Field label="Owners" hint="Select more than one for a joint account.">
              <div className="flex flex-wrap gap-3">
                {identities.map((i) => (
                  <label key={i.id} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={draft.owner_ids.includes(i.id)}
                      onChange={(e) =>
                        setDraft({ ...draft, owner_ids: e.target.checked ? [...draft.owner_ids, i.id] : draft.owner_ids.filter((x) => x !== i.id) })
                      }
                    />
                    {i.display_name}
                  </label>
                ))}
              </div>
            </Field>
            <ErrorNote error={error} />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDraft(null)}>
                Cancel
              </Button>
              <Button onClick={save} disabled={!draft.name || draft.currency.length !== 3}>
                Save
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
