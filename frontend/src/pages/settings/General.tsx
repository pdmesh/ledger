import { useEffect, useState } from "react";
import { Button, Card, ErrorNote, Field, Input, Select } from "../../components/ui";
import { api } from "../../lib/api";
import { useApp } from "../../lib/context";
import type { GeneralSettings } from "../../lib/types";

export default function General() {
  const { settings, refresh } = useApp();
  const [g, setG] = useState<GeneralSettings | null>(settings?.general ?? null);
  const [fx, setFx] = useState({ rate_date: "", from_currency: "", to_currency: settings?.general.base_currency ?? "", rate: "" });
  const [rates, setRates] = useState<{ id: number; rate_date: string; from_currency: string; to_currency: string; rate: string }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setG(settings?.general ?? null), [settings]);
  useEffect(() => {
    api.get<typeof rates>("/fx-rates").then(setRates);
  }, []);
  if (!g) return null;

  const save = async () => {
    setError(null);
    try {
      await api.put("/settings/general", g);
      await refresh();
      setMsg("Saved");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const addRate = async () => {
    try {
      await api.post("/fx-rates", fx);
      setRates(await api.get("/fx-rates"));
      setFx({ ...fx, rate: "" });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Region & formats">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Country">
            <Input value={g.country ?? ""} maxLength={2} onChange={(e) => setG({ ...g, country: e.target.value.toUpperCase() || null })} />
          </Field>
          <Field label="Base currency" hint="Changing it recomputes converted amounts.">
            <Input value={g.base_currency ?? ""} maxLength={3} onChange={(e) => setG({ ...g, base_currency: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Timezone">
            <Input value={g.timezone} onChange={(e) => setG({ ...g, timezone: e.target.value })} />
          </Field>
          <Field label="Locale">
            <Input value={g.locale} onChange={(e) => setG({ ...g, locale: e.target.value })} />
          </Field>
          <Field label="Statement date format">
            <Select className="w-full" value={g.date_format} onChange={(e) => setG({ ...g, date_format: e.target.value })}>
              <option value="auto">Auto-detect</option>
              <option value="DMY">Day / Month / Year</option>
              <option value="MDY">Month / Day / Year</option>
              <option value="YMD">Year / Month / Day</option>
            </Select>
          </Field>
          <Field label="Decimal separator">
            <Select className="w-full" value={g.decimal_separator} onChange={(e) => setG({ ...g, decimal_separator: e.target.value })}>
              <option value=".">Point (1,234.56)</option>
              <option value=",">Comma (1.234,56)</option>
            </Select>
          </Field>
        </div>
        <ErrorNote error={error} />
        <div className="mt-4 flex items-center justify-end gap-3">
          {msg && <span className="text-xs text-fg-muted">{msg}</span>}
          <Button onClick={save}>Save</Button>
        </div>
      </Card>
      <Card title="Exchange rates">
        <p className="mb-3 text-xs text-fg-muted">
          Original amounts are always kept. Foreign-currency transactions are converted to the base currency with the closest earlier rate
          (up to 10 days old).
        </p>
        <div className="grid grid-cols-[1fr_70px_70px_1fr_auto] items-end gap-2">
          <Field label="Date">
            <Input type="date" value={fx.rate_date} onChange={(e) => setFx({ ...fx, rate_date: e.target.value })} />
          </Field>
          <Field label="From">
            <Input value={fx.from_currency} maxLength={3} onChange={(e) => setFx({ ...fx, from_currency: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="To">
            <Input value={fx.to_currency} maxLength={3} onChange={(e) => setFx({ ...fx, to_currency: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Rate">
            <Input value={fx.rate} inputMode="decimal" onChange={(e) => setFx({ ...fx, rate: e.target.value })} />
          </Field>
          <Button variant="outline" onClick={addRate} disabled={!fx.rate_date || !fx.rate || fx.from_currency.length !== 3}>
            Add
          </Button>
        </div>
        <ul className="mt-3 max-h-48 space-y-0.5 overflow-y-auto text-xs text-fg-muted">
          {rates.map((r) => (
            <li key={r.id} className="num">
              {r.rate_date} · 1 {r.from_currency} = {r.rate} {r.to_currency}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
