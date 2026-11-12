import { Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Modal, Select, Toggle } from "../../components/ui";
import { api } from "../../lib/api";
import { categoryPath, useApp } from "../../lib/context";
import { humanize } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { ACCOUNT_TYPES, type Rule } from "../../lib/types";

interface Draft {
  id?: number;
  name: string;
  priority: number;
  words: string;
  regex: string;
  direction: string;
  account_types: string[];
  min_amount: string;
  max_amount: string;
  category: string;
  owner: string;
  active: boolean;
}

const blank: Draft = { name: "", priority: 50, words: "", regex: "", direction: "", account_types: [], min_amount: "", max_amount: "", category: "", owner: "", active: true };

export default function Rules() {
  const { categories, identities } = useApp();
  const rules = useApi<Rule[]>("/rules");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const slugName = (slug?: string) => {
    const c = categories.find((x) => x.slug === slug);
    return c ? categoryPath(categories, c.id) : slug;
  };

  const open = (r?: Rule) =>
    setDraft(
      r
        ? {
            id: r.id,
            name: r.name,
            priority: r.priority,
            words: (r.conditions.description_contains ?? []).join(", "),
            regex: r.conditions.description_regex ?? "",
            direction: r.conditions.direction ?? "",
            account_types: r.conditions.account_types ?? [],
            min_amount: r.conditions.min_amount ?? "",
            max_amount: r.conditions.max_amount ?? "",
            category: r.actions.category ?? "",
            owner: r.actions.owner_identity_id ? String(r.actions.owner_identity_id) : "",
            active: r.active,
          }
        : blank,
    );

  const save = async () => {
    if (!draft) return;
    const conditions: Rule["conditions"] = {};
    const words = draft.words.split(",").map((w) => w.trim()).filter(Boolean);
    if (words.length) conditions.description_contains = words;
    if (draft.regex) conditions.description_regex = draft.regex;
    if (draft.direction) conditions.direction = draft.direction as "inflow" | "outflow";
    if (draft.account_types.length) conditions.account_types = draft.account_types;
    if (draft.min_amount) conditions.min_amount = draft.min_amount;
    if (draft.max_amount) conditions.max_amount = draft.max_amount;
    const actions: Rule["actions"] = {};
    if (draft.category) actions.category = draft.category;
    if (draft.owner) actions.owner_identity_id = Number(draft.owner);
    const body = { name: draft.name, priority: draft.priority, conditions, actions, active: draft.active };
    setError(null);
    try {
      if (draft.id) await api.put(`/rules/${draft.id}`, body);
      else await api.post("/rules", body);
      setDraft(null);
      await rules.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const toggle = async (r: Rule) => {
    await api.put(`/rules/${r.id}`, { ...r, active: !r.active });
    await rules.reload();
  };

  return (
    <Card
      title="Classification rules"
      actions={
        <Button size="sm" onClick={() => open()}>
          <Plus size={14} /> Add rule
        </Button>
      }
    >
      <p className="mb-3 text-sm text-fg-muted">
        Rules run before AI. Your rules always run before the built-in ones; within each group, lower priority numbers run first. Saving a
        rule re-applies it to history.
      </p>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-fg-muted">
          <tr>
            <th className="pb-2 font-medium">Rule</th>
            <th className="pb-2 font-medium">When</th>
            <th className="pb-2 font-medium">Then</th>
            <th className="pb-2 font-medium">Active</th>
          </tr>
        </thead>
        <tbody>
          {(rules.data ?? []).map((r) => (
            <tr key={r.id} className="border-t border-border/60">
              <td className="py-1.5">
                <button className="hover:underline" onClick={() => open(r)}>
                  {r.name}
                </button>{" "}
                <Badge tone={r.source === "user" ? "accent" : "neutral"}>{r.source}</Badge>
              </td>
              <td className="py-1.5 text-xs text-fg-muted">
                {r.conditions.description_contains?.join(" / ")}
                {r.conditions.description_regex && ` /${r.conditions.description_regex}/`}
                {r.conditions.direction && ` · ${r.conditions.direction}`}
                {r.conditions.account_types?.length ? ` · ${r.conditions.account_types.map(humanize).join(", ")}` : ""}
              </td>
              <td className="py-1.5">{slugName(r.actions.category)}</td>
              <td className="py-1.5">
                <Toggle checked={r.active} onChange={() => toggle(r)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Modal open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? "Edit rule" : "New rule"}>
        {draft && (
          <div className="space-y-3">
            <div className="grid grid-cols-[1fr_100px] gap-3">
              <Field label="Name">
                <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </Field>
              <Field label="Priority">
                <Input type="number" value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) })} />
              </Field>
            </div>
            <Field label="Description contains any of" hint="Comma separated; matched on word boundaries, case-insensitive.">
              <Input value={draft.words} onChange={(e) => setDraft({ ...draft, words: e.target.value })} />
            </Field>
            <Field label="…or matches regular expression">
              <Input value={draft.regex} onChange={(e) => setDraft({ ...draft, regex: e.target.value })} />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Direction">
                <Select className="w-full" value={draft.direction} onChange={(e) => setDraft({ ...draft, direction: e.target.value })}>
                  <option value="">Either</option>
                  <option value="inflow">Inflow</option>
                  <option value="outflow">Outflow</option>
                </Select>
              </Field>
              <Field label="Min amount">
                <Input value={draft.min_amount} inputMode="decimal" onChange={(e) => setDraft({ ...draft, min_amount: e.target.value })} />
              </Field>
              <Field label="Max amount">
                <Input value={draft.max_amount} inputMode="decimal" onChange={(e) => setDraft({ ...draft, max_amount: e.target.value })} />
              </Field>
            </div>
            <Field label="Account types (optional)">
              <div className="flex flex-wrap gap-3">
                {ACCOUNT_TYPES.map((t) => (
                  <label key={t} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={draft.account_types.includes(t)}
                      onChange={(e) =>
                        setDraft({ ...draft, account_types: e.target.checked ? [...draft.account_types, t] : draft.account_types.filter((x) => x !== t) })
                      }
                    />
                    {humanize(t)}
                  </label>
                ))}
              </div>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Set category">
                <Select className="w-full" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                  <option value="">—</option>
                  {categories
                    .filter((c) => c.parent_id)
                    .map((c) => (
                      <option key={c.id} value={c.slug}>
                        {categoryPath(categories, c.id)}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field label="Attribute to">
                <Select className="w-full" value={draft.owner} onChange={(e) => setDraft({ ...draft, owner: e.target.value })}>
                  <option value="">Account owners</option>
                  {identities.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.display_name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <ErrorNote error={error} />
            <div className="flex justify-end">
              <Button onClick={save} disabled={!draft.name || !draft.category}>
                Save
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Card>
  );
}
