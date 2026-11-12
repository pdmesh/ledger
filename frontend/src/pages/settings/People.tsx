import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Modal, Select } from "../../components/ui";
import { api } from "../../lib/api";
import { useApp } from "../../lib/context";
import type { Identity } from "../../lib/types";

interface Draft {
  id?: number;
  display_name: string;
  legal_name: string;
  kind: "individual" | "household";
  aliases: string;
  identifiers: string;
}

export default function People() {
  const { identities, refresh } = useApp();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = (i?: Identity) =>
    setDraft(
      i
        ? { id: i.id, display_name: i.display_name, legal_name: i.legal_name ?? "", kind: i.kind, aliases: i.aliases.map((a) => a.alias).join(", "), identifiers: i.identifiers.join(", ") }
        : { display_name: "", legal_name: "", kind: "individual", aliases: "", identifiers: "" },
    );

  const save = async () => {
    if (!draft) return;
    const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
    const body = { display_name: draft.display_name, legal_name: draft.legal_name || null, kind: draft.kind, aliases: split(draft.aliases), identifiers: split(draft.identifiers) };
    setError(null);
    try {
      if (draft.id) await api.put(`/identities/${draft.id}`, body);
      else await api.post("/identities", body);
      setDraft(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const remove = async (i: Identity) => {
    if (!confirm(`Remove ${i.display_name}? Their accounts remain but lose this owner.`)) return;
    await api.del(`/identities/${i.id}`);
    await refresh();
  };

  return (
    <Card
      title="People & identities"
      actions={
        <Button size="sm" onClick={() => open()}>
          <Plus size={14} /> Add person
        </Button>
      }
    >
      <p className="mb-4 text-sm text-fg-muted">
        Aliases are matched against account-holder names on statements to work out who owns each account. Adding an alias re-checks every
        imported statement.
      </p>
      <ul className="divide-y divide-border">
        {identities.map((i) => (
          <li key={i.id} className="flex items-center justify-between gap-3 py-2.5">
            <div>
              <p className="font-medium">
                {i.display_name} {i.kind === "household" && <Badge>household</Badge>}
              </p>
              <p className="mt-0.5 flex flex-wrap gap-1">
                {i.legal_name && i.legal_name !== i.display_name && <Badge>{i.legal_name}</Badge>}
                {i.aliases.map((a) => (
                  <Badge key={a.id}>{a.alias}</Badge>
                ))}
              </p>
            </div>
            <div className="flex gap-1">
              <Button variant="outline" size="sm" onClick={() => open(i)}>
                Edit
              </Button>
              <Button variant="ghost" size="sm" onClick={() => remove(i)} aria-label="Remove">
                <Trash2 size={13} />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Modal open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? "Edit person" : "Add person"}>
        {draft && (
          <div className="space-y-3">
            <Field label="Display name">
              <Input value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} />
            </Field>
            <Field label="Full legal name (optional)">
              <Input value={draft.legal_name} onChange={(e) => setDraft({ ...draft, legal_name: e.target.value })} />
            </Field>
            <Field label="Aliases" hint="Comma separated: initials, abbreviations, spellings used by banks.">
              <Input value={draft.aliases} onChange={(e) => setDraft({ ...draft, aliases: e.target.value })} />
            </Field>
            <Field label="Other identifiers (optional)" hint="e.g. customer IDs or emails printed on statements.">
              <Input value={draft.identifiers} onChange={(e) => setDraft({ ...draft, identifiers: e.target.value })} />
            </Field>
            <Field label="Type">
              <Select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as Draft["kind"] })}>
                <option value="individual">Individual</option>
                <option value="household">Household</option>
              </Select>
            </Field>
            <ErrorNote error={error} />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDraft(null)}>
                Cancel
              </Button>
              <Button onClick={save} disabled={!draft.display_name.trim()}>
                Save
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Card>
  );
}
