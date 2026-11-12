import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { configureFormat, isoDate } from "./format";
import type { Account, AnalyticsFilters, Category, Identity, Settings } from "./types";

export type RangePreset = "3m" | "6m" | "12m" | "ytd" | "all" | "custom";

export interface ViewScope {
  scope: "household" | "individual" | "joint";
  identityId?: number;
  preset: RangePreset;
  from?: string;
  to?: string;
}

interface AppState {
  settings: Settings | null;
  identities: Identity[];
  accounts: Account[];
  categories: Category[];
  view: ViewScope;
  setView: (v: ViewScope) => void;
  filters: AnalyticsFilters;
  refresh: () => Promise<void>;
  ready: boolean;
  error: string | null;
}

const Ctx = createContext<AppState | null>(null);

function rangeFor(v: ViewScope): { from?: string; to?: string } {
  const now = new Date();
  const back = (months: number) => isoDate(new Date(now.getFullYear(), now.getMonth() - months + 1, 1));
  switch (v.preset) {
    case "3m":
      return { from: back(3) };
    case "6m":
      return { from: back(6) };
    case "12m":
      return { from: back(12) };
    case "ytd":
      return { from: `${now.getFullYear()}-01-01` };
    case "custom":
      return { from: v.from, to: v.to };
    default:
      return {};
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewScope>(() => {
    try {
      const raw = localStorage.getItem("ledger.view");
      if (raw) return JSON.parse(raw) as ViewScope;
    } catch {
      /* ignore */
    }
    return { scope: "household", preset: "all" };
  });

  const refresh = useCallback(async () => {
    try {
      const [s, i, a, c] = await Promise.all([
        api.get<Settings>("/settings"),
        api.get<Identity[]>("/identities"),
        api.get<Account[]>("/accounts"),
        api.get<Category[]>("/categories"),
      ]);
      configureFormat(s.general.base_currency, s.general.locale);
      setSettings(s);
      setIdentities(i);
      setAccounts(a);
      setCategories(c);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    try {
      localStorage.setItem("ledger.view", JSON.stringify(view));
    } catch {
      /* ignore */
    }
  }, [view]);

  const filters = useMemo<AnalyticsFilters>(() => {
    const r = rangeFor(view);
    return {
      date_from: r.from,
      date_to: r.to,
      scope: view.scope,
      identity_id: view.scope === "individual" ? view.identityId : undefined,
    };
  }, [view]);

  return (
    <Ctx.Provider
      value={{ settings, identities, accounts, categories, view, setView, filters, refresh, ready: !!settings, error }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

export function categoryPath(categories: Category[], id: number | null): string {
  if (id == null) return "Uncategorized";
  const byId = new Map(categories.map((c) => [c.id, c]));
  const c = byId.get(id);
  if (!c) return "—";
  const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
  return parent && parent.parent_id ? `${parent.name} › ${c.name}` : c.name;
}
