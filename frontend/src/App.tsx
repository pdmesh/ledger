import { BarChart3, FileInput, LayoutDashboard, Landmark, ListOrdered, Settings as SettingsIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { ScopeBar } from "./components/ScopeBar";
import { cn, ErrorNote } from "./components/ui";
import { backendStatus, type BackendStatus } from "./lib/api";
import { useApp } from "./lib/context";
import AccountsPage from "./pages/Accounts";
import AnalyticsPage from "./pages/Analytics";
import ImportCentre from "./pages/ImportCentre";
import Onboarding from "./pages/Onboarding";
import OverviewPage from "./pages/Overview";
import SettingsPage from "./pages/Settings";
import TransactionsPage from "./pages/Transactions";

export type Section = "overview" | "transactions" | "accounts" | "import" | "analytics" | "settings";

const NAV: { id: Section; label: string; icon: ReactNode }[] = [
  { id: "overview", label: "Overview", icon: <LayoutDashboard size={16} /> },
  { id: "transactions", label: "Transactions", icon: <ListOrdered size={16} /> },
  { id: "accounts", label: "Accounts", icon: <Landmark size={16} /> },
  { id: "import", label: "Import Centre", icon: <FileInput size={16} /> },
  { id: "analytics", label: "Analytics", icon: <BarChart3 size={16} /> },
  { id: "settings", label: "Settings", icon: <SettingsIcon size={16} /> },
];

/** Cross-page navigation with an optional transaction filter (e.g. "show me these"). */
export interface NavTarget {
  section: Section;
  txnFilter?: Record<string, string | number | (string | number)[]>;
}

export default function App() {
  const { ready, settings, error } = useApp();
  const [nav, setNav] = useState<NavTarget>({ section: "overview" });

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        {error ? <BackendError message={error} /> : <p className="text-fg-muted">Starting the local backend…</p>}
      </div>
    );
  }
  if (!settings?.general.onboarding_complete) return <Onboarding />;

  const go = (t: NavTarget) => setNav(t);
  const showScope = nav.section === "overview" || nav.section === "analytics" || nav.section === "transactions";

  return (
    <div className="flex h-full">
      <nav className="flex w-52 shrink-0 flex-col border-r border-border bg-surface">
        <div className="px-4 py-4 text-sm font-semibold tracking-tight">Ledger</div>
        <ul className="flex-1 space-y-0.5 px-2">
          {NAV.map((n) => (
            <li key={n.id}>
              <button
                onClick={() => go({ section: n.id })}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm",
                  nav.section === n.id ? "bg-muted font-medium text-fg" : "text-fg-muted hover:bg-muted/60 hover:text-fg",
                )}
              >
                {n.icon}
                {n.label}
              </button>
            </li>
          ))}
        </ul>
        <p className="px-4 py-3 text-[11px] text-fg-subtle">Local-first · data stays on this device</p>
      </nav>
      <main className="flex min-w-0 flex-1 flex-col">
        {showScope && <ScopeBar />}
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {nav.section === "overview" && <OverviewPage go={go} />}
          {nav.section === "transactions" && <TransactionsPage initialFilter={nav.txnFilter} />}
          {nav.section === "accounts" && <AccountsPage go={go} />}
          {nav.section === "import" && <ImportCentre />}
          {nav.section === "analytics" && <AnalyticsPage go={go} />}
          {nav.section === "settings" && <SettingsPage />}
        </div>
      </main>
    </div>
  );
}

function BackendError({ message }: { message: string }) {
  const { refresh } = useApp();
  const [status, setStatus] = useState<BackendStatus | null>(null);
  useEffect(() => {
    backendStatus().then(setStatus).catch(() => setStatus(null));
  }, []);
  return (
    <div className="w-full max-w-3xl space-y-3">
      <ErrorNote error={`Cannot reach the local backend: ${message}`} />
      {status && (
        <div className="space-y-2 text-sm">
          <p className="text-fg-muted">
            Backend at {status.url} is {status.running ? "running" : "not running"}
            {status.exit_code !== null && ` (exit code ${status.exit_code})`}. Full log: <code>{status.log_file}</code>
          </p>
          {status.log_tail.length > 0 && (
            <pre className="max-h-80 overflow-auto rounded-md bg-muted p-3 text-[11px] leading-relaxed">{status.log_tail.join("\n")}</pre>
          )}
        </div>
      )}
      <button className="text-sm text-accent hover:underline" onClick={() => void refresh()}>
        Try again
      </button>
    </div>
  );
}
