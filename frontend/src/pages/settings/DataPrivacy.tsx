import { useState } from "react";
import { Badge, Button, Card, ErrorNote, confirmAction } from "../../components/ui";
import { api } from "../../lib/api";
import { bytes } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import type { ConfigChange } from "../../lib/types";

export default function DataPrivacy() {
  const history = useApi<ConfigChange[]>("/config/history", { limit: 100 });
  const [backup, setBackup] = useState<{ name: string; path: string; size_bytes: number } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const makeBackup = async () => {
    setError(null);
    try {
      setBackup(await api.post("/backup"));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const restore = async () => {
    if (!backup) return;
    const ok = await confirmAction({
      title: "Restore this backup?",
      body: "The current ledger will be replaced with this backup the next time the app starts.",
      confirmLabel: "Restore on restart",
      danger: true,
    });
    if (!ok) return;
    const r = await api.post<{ message: string }>("/restore", { name: backup.name });
    setMsg(r.message);
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Where your data lives">
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-fg-muted">
          <li>The ledger is a SQLite database in the application data folder on this device.</li>
          <li>Imported statements are copied, unmodified, into a local archive next to it.</li>
          <li>Only the last four digits of account and card numbers are stored.</li>
          <li>API keys are kept in the operating system keychain, never in the database.</li>
          <li>Nothing leaves this device unless you enable a cloud or CLI provider in Intelligence settings.</li>
          <li>Deleting a document in the Import Centre removes its file and every transaction extracted from it.</li>
        </ul>
      </Card>
      <Card title="Backup & restore">
        <p className="mb-3 text-sm text-fg-muted">A backup is a single zip with the database and every archived statement.</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={makeBackup}>Create backup</Button>
          {backup && (
            <>
              <Button variant="outline" onClick={async () => window.open(await api.fileUrl(`/backup/${backup.name}`), "_blank")}>
                Download ({bytes(backup.size_bytes)})
              </Button>
              <Button variant="ghost" onClick={restore}>
                Restore this backup…
              </Button>
            </>
          )}
        </div>
        {backup && <p className="mt-2 break-all text-xs text-fg-subtle">{backup.path}</p>}
        {msg && <p className="mt-2 text-sm text-accent">{msg}</p>}
        <ErrorNote error={error} />
      </Card>
      <Card title="Configuration history" className="lg:col-span-2">
        <p className="mb-3 text-xs text-fg-muted">
          Every configuration change is versioned. Each transaction records the configuration version it was classified with.
        </p>
        <table className="w-full text-sm">
          <tbody>
            {(history.data ?? []).map((h) => (
              <tr key={h.id} className="border-t border-border/60">
                <td className="num py-1.5 pr-3 text-xs text-fg-subtle">v{h.global_version}</td>
                <td className="py-1.5 pr-3 text-xs text-fg-subtle">{new Date(h.created_at).toLocaleString()}</td>
                <td className="py-1.5 pr-3">
                  <Badge>{h.scope}</Badge>
                </td>
                <td className="py-1.5 pr-3">{h.summary}</td>
                <td className="py-1.5">
                  {h.propagation !== "none" && <Badge tone={h.propagation === "ai" ? "warning" : "accent"}>{h.propagation === "ai" ? "AI re-classification" : "re-applied"}</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
