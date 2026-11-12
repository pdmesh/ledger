import { Cloud, HardDrive, KeyRound, Terminal, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Select, Toggle } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import type { IntelligenceConfig, ProviderConfig } from "../../lib/types";

const KIND_ICON = { local: <HardDrive size={13} />, api: <Cloud size={13} />, cli: <Terminal size={13} /> };

interface Exec {
  id: number;
  task: string;
  provider_id: string;
  model: string | null;
  status: string;
  error: string | null;
  cost_usd: number | null;
  latency_ms: number | null;
  item_count: number;
  created_at: string;
}

export default function Intelligence() {
  const cfg = useApi<IntelligenceConfig>("/intelligence");
  const execs = useApi<{ items: Exec[]; totals: { task: string; provider_id: string; calls: number; cost_usd: number | null }[] }>("/intelligence/executions", { limit: 30 });
  const [draft, setDraft] = useState<IntelligenceConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [cli, setCli] = useState<Record<string, { found: boolean; version?: string; path?: string }>>({});

  useEffect(() => setDraft(cfg.data), [cfg.data]);
  if (!draft) return <ErrorNote error={cfg.error} />;

  const upd = (i: number, p: Partial<ProviderConfig>) => setDraft({ ...draft, providers: draft.providers.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  const addFrom = (t: IntelligenceConfig["templates"][number]) => {
    const base = (t.cli ?? t.label ?? "provider").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30);
    let id = base;
    let n = 2;
    while (draft.providers.some((p) => p.id === id)) id = `${base}-${n++}`;
    setDraft({ ...draft, providers: [...draft.providers, { id, kind: t.kind!, label: t.label, model: t.model ?? null, api_base: t.api_base ?? null, cli: t.cli ?? null, enabled: true }] });
  };
  const save = async () => {
    setError(null);
    try {
      const body = {
        providers: draft.providers.map(({ has_key: _hk, ...p }) => p),
        routing: Object.fromEntries(Object.entries(draft.routing).filter(([, v]) => v.length)),
        allow_cloud: draft.allow_cloud,
        share_identity_names: draft.share_identity_names,
        batch_size: draft.batch_size,
      };
      await api.put("/intelligence", body);
      await cfg.reload();
      setMsg("Saved");
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };
  const storeKey = async (id: string) => {
    try {
      await api.put(`/intelligence/providers/${id}/key`, { api_key: keys[id] || null });
      setKeys({ ...keys, [id]: "" });
      await cfg.reload();
      setMsg("Key stored in the OS keychain");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const test = async (id: string) => {
    setError(null);
    // The backend tests the saved configuration, so save pending edits first.
    if (!(await save())) return;
    setMsg(`Testing ${id}… (CLI providers can take up to a minute)`);
    try {
      const r = await api.post<{ ok: boolean; error?: string; latency_ms?: number; model?: string }>(`/intelligence/providers/${id}/test`);
      setMsg(r.ok ? `${id}: OK (${r.model}, ${r.latency_ms} ms)` : `${id}: ${r.error ?? "unexpected response"}`);
    } catch (e) {
      setMsg(null);
      setError(`${id}: ${(e as Error).message}`);
    }
  };
  const detect = async (name: string, executable?: string | null) => {
    try {
      setCli({ ...cli, [name]: await api.get(`/intelligence/cli/${name}`, executable ? { executable } : undefined) });
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const route = (task: string) => draft.routing[task] ?? [];
  const setRoute = (task: string, idx: number, val: string) => {
    const chain = [...route(task)];
    if (val) chain[idx] = val;
    else chain.splice(idx, 1);
    setDraft({ ...draft, routing: { ...draft.routing, [task]: chain.filter(Boolean) } });
  };

  return (
    <div className="space-y-5">
      <Card title="Privacy">
        <div className="space-y-3">
          <Toggle
            checked={draft.allow_cloud}
            onChange={(v) => setDraft({ ...draft, allow_cloud: v })}
            label={<span>Allow cloud and CLI providers <span className="text-xs text-fg-muted">— transaction descriptions and amounts are sent to them. Local providers are always allowed.</span></span>}
          />
          <Toggle
            checked={draft.share_identity_names}
            onChange={(v) => setDraft({ ...draft, share_identity_names: v })}
            label={<span>Share household names with cloud providers <span className="text-xs text-fg-muted">— otherwise replaced by “Person 1”, “Person 2”.</span></span>}
          />
          <p className="text-xs text-fg-muted">
            With no provider configured the ledger runs fully deterministically: rules, merchant mappings and your corrections still classify
            transactions; anything else is marked uncategorized with low confidence.
          </p>
        </div>
      </Card>

      <Card
        title="Providers"
        actions={
          <Select value="" onChange={(e) => e.target.value && addFrom(draft.templates[Number(e.target.value)])}>
            <option value="">Add provider…</option>
            {draft.templates.map((t, i) => (
              <option key={i} value={i}>
                {t.label}
              </option>
            ))}
          </Select>
        }
      >
        {draft.providers.length === 0 && <p className="text-sm text-fg-muted">No providers yet.</p>}
        <div className="space-y-4">
          {draft.providers.map((p, i) => (
            <div key={i} className="rounded-md border border-border p-3">
              <div className="mb-3 flex items-center gap-2">
                <Badge tone={p.kind === "local" ? "positive" : "warning"}>
                  {KIND_ICON[p.kind]} {p.kind}
                </Badge>
                <span className="text-sm font-medium">{p.label ?? p.id}</span>
                <span className="ml-auto flex items-center gap-2">
                  <Toggle checked={p.enabled !== false} onChange={(v) => upd(i, { enabled: v })} />
                  <Button size="sm" variant="outline" onClick={() => test(p.id)}>
                    Test
                  </Button>
                  <Button size="sm" variant="ghost" aria-label="Remove" onClick={() => setDraft({ ...draft, providers: draft.providers.filter((_, j) => j !== i) })}>
                    <Trash2 size={13} />
                  </Button>
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="ID">
                  <Input value={p.id} onChange={(e) => upd(i, { id: e.target.value })} />
                </Field>
                {p.kind !== "cli" ? (
                  <>
                    <Field label="Model" hint="LiteLLM model string, e.g. anthropic/<model>, ollama_chat/<model>.">
                      <Input value={p.model ?? ""} onChange={(e) => upd(i, { model: e.target.value })} />
                    </Field>
                    <Field label="API base (optional)">
                      <Input value={p.api_base ?? ""} onChange={(e) => upd(i, { api_base: e.target.value || null })} />
                    </Field>
                  </>
                ) : (
                  <>
                    <Field label="Executable" hint="Official CLI, installed and logged in by you.">
                      <Input value={p.executable ?? ""} placeholder={p.cli ?? ""} onChange={(e) => upd(i, { executable: e.target.value || null })} />
                    </Field>
                    <Field label="Model (optional)">
                      <Input value={p.model ?? ""} onChange={(e) => upd(i, { model: e.target.value || null })} />
                    </Field>
                  </>
                )}
              </div>
              {p.kind === "api" && (
                <div className="mt-3 flex items-end gap-2">
                  <Field label={p.has_key ? "API key (stored — enter a new one to replace)" : "API key"}>
                    <Input type="password" autoComplete="off" value={keys[p.id] ?? ""} onChange={(e) => setKeys({ ...keys, [p.id]: e.target.value })} />
                  </Field>
                  <Button variant="outline" onClick={() => storeKey(p.id)}>
                    <KeyRound size={13} /> Store in keychain
                  </Button>
                </div>
              )}
              {p.kind === "cli" && p.cli && (
                <div className="mt-3 flex items-center gap-2 text-xs">
                  <Button size="sm" variant="outline" onClick={() => detect(p.cli!, p.executable)}>
                    Detect
                  </Button>
                  {cli[p.cli] && (cli[p.cli].found ? <span className="text-positive">Found {cli[p.cli].version}</span> : <span className="text-negative">Not found on PATH</span>)}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Task routing">
        <p className="mb-3 text-xs text-fg-muted">
          Choose a model per task, with fallbacks tried in order. Tasks without a route use “default”. Use small/local models for routine
          classification and reserve stronger ones for extraction and adjudication.
        </p>
        <table className="w-full text-sm">
          <tbody>
            {["default", ...Object.keys(draft.tasks)].map((task) => (
              <tr key={task} className="border-t border-border/60">
                <td className="py-2 pr-3">
                  <p className="font-medium">{task}</p>
                  <p className="text-[11px] text-fg-subtle">{draft.tasks[task] ?? "Used when a task has no route"}</p>
                </td>
                <td className="py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {[...route(task), ""].map((pid, idx) => (
                      <Select key={idx} value={pid} onChange={(e) => setRoute(task, idx, e.target.value)}>
                        <option value="">{idx === 0 ? "—" : "+ fallback"}</option>
                        {draft.providers.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.id}
                          </option>
                        ))}
                      </Select>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <ErrorNote error={error} />
      <div className="flex items-center justify-end gap-3">
        {msg && <span className="text-xs text-fg-muted">{msg}</span>}
        <Button onClick={save}>
          Save providers & routing
        </Button>
      </div>

      <Card title="Recent model calls">
        <div className="mb-3 flex flex-wrap gap-2 text-xs">
          {(execs.data?.totals ?? []).map((t) => (
            <Badge key={`${t.task}-${t.provider_id}`}>
              {t.task} · {t.provider_id}: {t.calls} calls{t.cost_usd ? ` · $${t.cost_usd.toFixed(4)}` : ""}
            </Badge>
          ))}
        </div>
        <table className="w-full text-xs">
          <tbody>
            {(execs.data?.items ?? []).map((e) => (
              <tr key={e.id} className="border-t border-border/60">
                <td className="py-1 pr-2 text-fg-subtle">{new Date(e.created_at).toLocaleString()}</td>
                <td className="py-1 pr-2">{e.task}</td>
                <td className="py-1 pr-2">
                  {e.provider_id} / {e.model}
                </td>
                <td className="py-1 pr-2">
                  <Badge tone={e.status === "ok" ? "positive" : "negative"}>{e.status}</Badge>
                </td>
                <td className="num py-1 pr-2">{e.item_count} items</td>
                <td className="num py-1 pr-2">{e.latency_ms ?? "—"} ms</td>
                <td className="py-1 text-negative">{e.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
