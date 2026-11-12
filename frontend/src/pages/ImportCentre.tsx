import { FileUp, FolderSync, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useRef, useState, type DragEvent } from "react";
import { Badge, Button, Card, Drawer, Empty, ErrorNote, Field, Input, Toggle, cn } from "../components/ui";
import { api } from "../lib/api";
import { useApp } from "../lib/context";
import { bytes, date, humanize } from "../lib/format";
import { useApi, usePoll } from "../lib/hooks";
import type { DocumentInfo, Job } from "../lib/types";

const STATUS_TONE: Record<DocumentInfo["status"], "neutral" | "positive" | "negative" | "warning" | "accent"> = {
  queued: "neutral",
  processing: "accent",
  processed: "positive",
  failed: "negative",
  duplicate: "warning",
};

export default function ImportCentre() {
  const { settings, refresh } = useApp();
  const docs = useApi<DocumentInfo[]>("/documents");
  const jobs = useApi<Job[]>("/jobs", { limit: 15 });
  const summary = useApi<{ documents: Record<string, number>; reconciliation: Record<string, number>; pending_jobs: number }>("/documents/summary");
  const [drag, setDrag] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DocumentInfo | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [folder, setFolder] = useState(settings?.ingestion.watch_folder ?? "");

  const busy = (summary.data?.pending_jobs ?? 0) > 0 || (docs.data ?? []).some((d) => d.status === "queued" || d.status === "processing");
  const reloadAll = useCallback(() => {
    void docs.reload();
    void jobs.reload();
    void summary.reload();
    if (!busy) void refresh();
  }, [docs, jobs, summary, busy, refresh]);
  usePoll(reloadAll, busy, 1500);

  const upload = async (files: FileList | File[]) => {
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    setError(null);
    try {
      const r = await api.post<{ results: { filename: string; status: string; error?: string }[] }>("/documents", fd);
      setNotes(r.results.map((x) => `${x.filename}: ${x.status}${x.error ? ` — ${x.error}` : ""}`));
      reloadAll();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files.length) void upload(e.dataTransfer.files);
  };

  const saveFolder = async (enabled: boolean) => {
    await api.put("/settings/ingestion", { watch_folder: folder || null, watch_enabled: enabled && !!folder });
    await refresh();
    reloadAll();
  };

  const remove = async (d: DocumentInfo) => {
    if (!confirm(`Delete ${d.original_filename} and all ${d.stats.inserted ?? 0} transactions extracted from it?`)) return;
    await api.del(`/documents/${d.id}`);
    setSelected(null);
    reloadAll();
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
            drag ? "border-accent bg-accent/5" : "border-border bg-surface hover:bg-muted/40",
          )}
        >
          <FileUp className="text-fg-subtle" />
          <p className="text-sm font-medium">Drop statements here, or click to choose</p>
          <p className="text-xs text-fg-muted">PDF, CSV, XLSX and XLS from any bank or card. Re-importing the same file is safe.</p>
          <input ref={inputRef} type="file" multiple hidden accept=".pdf,.csv,.xlsx,.xls,.tsv,.txt" onChange={(e) => e.target.files && upload(e.target.files)} />
        </div>
        <Card title={<span className="flex items-center gap-2"><FolderSync size={14} /> Watched folder</span>}>
          <div className="space-y-3">
            <Field label="Folder path" hint="New files in this folder are imported automatically.">
              <Input value={folder} placeholder="~/Documents/Statements" onChange={(e) => setFolder(e.target.value)} />
            </Field>
            <div className="flex items-center justify-between">
              <Toggle checked={!!settings?.ingestion.watch_enabled} onChange={saveFolder} label="Watch" />
              <Button variant="outline" size="sm" onClick={async () => { await api.post("/documents/scan-folder"); reloadAll(); }} disabled={!settings?.ingestion.watch_folder}>
                Scan now
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <ErrorNote error={error} />
      {notes.length > 0 && (
        <ul className="rounded-md border border-border bg-surface px-4 py-2 text-sm text-fg-muted">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      {summary.data && (
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(summary.data.documents).map(([k, v]) => (
            <Badge key={k} tone={STATUS_TONE[k as DocumentInfo["status"]] ?? "neutral"}>
              {v} {k}
            </Badge>
          ))}
          {Object.entries(summary.data.reconciliation).map(([k, v]) => (
            <Badge key={k}>
              {v} {humanize(k)} links
            </Badge>
          ))}
          {busy && (
            <Badge tone="accent">
              <RefreshCw size={11} className="animate-spin" /> processing
            </Badge>
          )}
        </div>
      )}

      {docs.data?.length === 0 ? (
        <Empty title="Nothing imported yet" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-fg-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Document</th>
                <th className="px-3 py-2 font-medium">Identified as</th>
                <th className="px-3 py-2 font-medium">Period</th>
                <th className="px-3 py-2 font-medium">Transactions</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {docs.data?.map((d) => (
                <tr key={d.id} className="cursor-pointer border-b border-border/60 last:border-0 hover:bg-muted/50" onClick={() => setSelected(d)}>
                  <td className="px-3 py-2">
                    <p className="font-medium">{d.original_filename}</p>
                    <p className="text-xs text-fg-subtle">
                      {d.file_format.toUpperCase()} · {bytes(d.size_bytes)} · {date(d.created_at)}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <p>{d.account ?? "—"}</p>
                    <p className="text-xs text-fg-subtle">{humanize(d.document_type)}</p>
                  </td>
                  <td className="num whitespace-nowrap px-3 py-2 text-fg-muted">
                    {date(d.statement_start)} – {date(d.statement_end)}
                  </td>
                  <td className="num px-3 py-2">
                    {d.stats.inserted ?? "—"}
                    {(d.stats.duplicates_across_documents ?? 0) > 0 && (
                      <span className="ml-1 text-xs text-fg-subtle">({d.stats.duplicates_across_documents} already known)</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap items-center gap-1">
                      <Badge tone={STATUS_TONE[d.status]}>{d.status}</Badge>
                      {d.warnings.length > 0 && <Badge tone="warning">{d.warnings.length} warning{d.warnings.length > 1 ? "s" : ""}</Badge>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Card title="Background activity">
        <ul className="space-y-1 text-xs">
          {(jobs.data ?? []).map((j) => (
            <li key={j.id} className="flex flex-wrap items-center gap-2">
              <Badge tone={j.status === "failed" ? "negative" : j.status === "done" ? "positive" : "accent"}>{j.status}</Badge>
              <span>{humanize(j.kind)}</span>
              <span className="text-fg-subtle">{new Date(j.created_at).toLocaleString()}</span>
              {j.error && <span className="text-negative">{j.error}</span>}
              {j.status === "failed" && (
                <Button variant="ghost" size="sm" onClick={async () => { await api.post(`/jobs/${j.id}/retry`); reloadAll(); }}>
                  Retry
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.original_filename ?? ""}>
        {selected && (
          <div className="space-y-4 text-sm">
            {selected.error && <ErrorNote error={selected.error} />}
            {selected.warnings.length > 0 && (
              <ul className="list-disc space-y-1 rounded-md bg-warning/10 px-6 py-2 text-warning">
                {selected.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
            <dl className="grid grid-cols-[150px_1fr] gap-y-1.5">
              <dt className="text-fg-muted">Institution</dt>
              <dd>{selected.institution ?? "—"}</dd>
              <dt className="text-fg-muted">Account</dt>
              <dd>{selected.account ?? "—"}</dd>
              <dt className="text-fg-muted">Type</dt>
              <dd>{humanize(selected.document_type)}</dd>
              <dt className="text-fg-muted">Extraction</dt>
              <dd>{selected.extraction_method}</dd>
              <dt className="text-fg-muted">Currency</dt>
              <dd>{selected.currency ?? "—"}</dd>
              <dt className="text-fg-muted">Opening / closing</dt>
              <dd className="num">
                {selected.opening_balance ?? "—"} / {selected.closing_balance ?? "—"}
              </dd>
            </dl>
            <div>
              <p className="mb-1 text-xs font-medium text-fg-muted">Identification evidence</p>
              <pre className="overflow-x-auto rounded bg-muted px-2 py-1.5 text-[11px]">{JSON.stringify(selected.identification, null, 2)}</pre>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-fg-muted">Processing statistics</p>
              <pre className="overflow-x-auto rounded bg-muted px-2 py-1.5 text-[11px]">{JSON.stringify(selected.stats, null, 2)}</pre>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={async () => window.open(await api.fileUrl(`/documents/${selected.id}/file`), "_blank")}>
                Open original
              </Button>
              <Button variant="outline" size="sm" onClick={async () => { await api.post(`/documents/${selected.id}/reprocess`).catch((e) => setError(e.message)); setSelected(null); reloadAll(); }}>
                Re-process
              </Button>
              <Button variant="danger" size="sm" onClick={() => remove(selected)}>
                <Trash2 size={13} /> Delete
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
