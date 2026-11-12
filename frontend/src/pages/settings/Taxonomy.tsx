import { Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Modal, Select } from "../../components/ui";
import { api } from "../../lib/api";
import { useApp } from "../../lib/context";
import { ROLES, ROLE_LABEL, type Category, type Role } from "../../lib/types";

type Mode = { kind: "edit"; cat: Category } | { kind: "add"; parentId: number | null } | { kind: "merge"; cat: Category } | null;

export default function Taxonomy() {
  const { categories, refresh } = useApp();
  const [mode, setMode] = useState<Mode>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [parent, setParent] = useState<number | "">("");
  const [role, setRole] = useState<Role>("expense");
  const [target, setTarget] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const roots = categories.filter((c) => !c.parent_id);
  const childrenOf = (id: number) => categories.filter((c) => c.parent_id === id);

  const openEdit = (c: Category) => {
    setMode({ kind: "edit", cat: c });
    setName(c.name);
    setDesc(c.description);
    setParent(c.parent_id ?? "");
    setError(null);
  };
  const openAdd = (parentId: number | null) => {
    setMode({ kind: "add", parentId });
    setName("");
    setDesc("");
    setParent(parentId ?? "");
    setError(null);
  };

  const submit = async () => {
    setError(null);
    try {
      if (mode?.kind === "edit") {
        const r = await api.patch<{ propagation: string }>(`/categories/${mode.cat.id}`, {
          name,
          description: desc,
          ...(mode.cat.parent_id && parent !== mode.cat.parent_id ? { parent_id: parent } : {}),
        });
        setNotice(
          r.propagation === "ai"
            ? "Meaning changed — affected transactions are being re-classified in the background."
            : r.propagation === "deterministic"
              ? "Moved — analytics updated."
              : "Renamed — shown everywhere immediately.",
        );
      } else if (mode?.kind === "add") {
        await api.post("/categories", { name, description: desc, parent_id: parent || null, role: parent ? undefined : role });
        setNotice("Category added. Uncategorized transactions will be re-checked against it.");
      } else if (mode?.kind === "merge" && target) {
        const r = await api.post<{ moved_transactions: number }>(`/categories/${mode.cat.id}/merge-into/${target}`);
        setNotice(`Merged; ${r.moved_transactions} transactions moved.`);
      }
      setMode(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const toggle = async (c: Category) => {
    try {
      await api.patch(`/categories/${c.id}`, { active: !c.active });
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const node = (c: Category, depth: number) => (
    <div key={c.id}>
      <div className="group flex items-center gap-2 rounded px-2 py-1.5 hover:bg-muted/50" style={{ paddingLeft: 8 + depth * 18 }}>
        <span className={depth === 0 ? "font-semibold" : ""}>{c.name}</span>
        {c.transaction_count ? <span className="text-xs text-fg-subtle">{c.transaction_count}</span> : null}
        {c.description && <span className="hidden truncate text-xs text-fg-subtle md:inline">— {c.description}</span>}
        <span className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100">
          <Button size="sm" variant="ghost" onClick={() => openAdd(c.id)}>
            <Plus size={12} /> Sub
          </Button>
          <Button size="sm" variant="ghost" onClick={() => openEdit(c)}>
            Edit
          </Button>
          {c.parent_id && (
            <Button size="sm" variant="ghost" onClick={() => { setMode({ kind: "merge", cat: c }); setTarget(""); }}>
              Merge
            </Button>
          )}
          {c.parent_id && !c.is_system && (
            <Button size="sm" variant="ghost" onClick={() => toggle(c)}>
              Disable
            </Button>
          )}
        </span>
      </div>
      {childrenOf(c.id).map((k) => node(k, depth + 1))}
    </div>
  );

  return (
    <Card
      title="Taxonomy"
      actions={
        <Button size="sm" variant="outline" onClick={() => openAdd(null)}>
          <Plus size={14} /> New type
        </Button>
      }
    >
      <p className="mb-3 text-sm text-fg-muted">
        Each top-level type has an analytic role (income, expense, investment, movement, adjustment) that decides how it counts. Rename,
        move, merge or describe categories freely — historical transactions follow.
      </p>
      {notice && <p className="mb-3 rounded-md bg-accent/10 px-3 py-2 text-sm text-accent">{notice}</p>}
      <div className="text-sm">{roots.map((r) => node(r, 0))}</div>

      <Modal open={!!mode} onClose={() => setMode(null)} title={mode?.kind === "merge" ? `Merge “${mode.cat.name}”` : mode?.kind === "edit" ? "Edit category" : "New category"}>
        {mode?.kind === "merge" ? (
          <div className="space-y-3">
            <p className="text-sm text-fg-muted">All transactions, merchant mappings and rules using this category will move to:</p>
            <Select className="w-full" value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Choose…</option>
              {categories
                .filter((c) => c.parent_id && c.id !== mode.cat.id)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {ROLE_LABEL[c.role]} › {c.name}
                  </option>
                ))}
            </Select>
            <ErrorNote error={error} />
            <div className="flex justify-end">
              <Button disabled={!target} onClick={submit}>
                Merge
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Description" hint="Used by AI classification; changing it re-classifies AI-decided transactions in this category.">
              <Input value={desc} onChange={(e) => setDesc(e.target.value)} />
            </Field>
            {(mode?.kind === "add" ? parent !== "" : mode?.kind === "edit" && mode.cat.parent_id) ? (
              <Field label="Parent">
                <Select className="w-full" value={parent} onChange={(e) => setParent(Number(e.target.value))}>
                  {categories
                    .filter((c) => mode?.kind !== "edit" || c.id !== mode.cat.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.parent_id ? `   ${c.name}` : c.name}
                      </option>
                    ))}
                </Select>
              </Field>
            ) : mode?.kind === "add" ? (
              <Field label="Analytic role">
                <Select className="w-full" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABEL[r]}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : (
              <Badge>Top-level type · role {mode?.kind === "edit" ? ROLE_LABEL[mode.cat.role] : ""}</Badge>
            )}
            <ErrorNote error={error} />
            <div className="flex justify-end">
              <Button disabled={!name.trim()} onClick={submit}>
                Save
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Card>
  );
}
