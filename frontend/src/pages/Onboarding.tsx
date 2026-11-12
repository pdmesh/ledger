import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Card, ErrorNote, Field, Input, Select } from "../components/ui";
import { api } from "../lib/api";
import { useApp } from "../lib/context";

interface Preset {
  base_currency: string;
  date_format: string;
  timezone: string;
}

interface PersonDraft {
  display_name: string;
  aliases: string;
}

export default function Onboarding() {
  const { refresh } = useApp();
  const [step, setStep] = useState(0);
  const [presets, setPresets] = useState<Record<string, Preset>>({});
  const [country, setCountry] = useState("");
  const [currency, setCurrency] = useState("");
  const [dateFormat, setDateFormat] = useState("auto");
  const [people, setPeople] = useState<PersonDraft[]>([{ display_name: "", aliases: "" }]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<{ countries: Record<string, Preset> }>("/onboarding/presets").then((r) => setPresets(r.countries));
  }, []);

  const pickCountry = (c: string) => {
    setCountry(c);
    const p = presets[c];
    if (p) {
      setCurrency(p.base_currency);
      setDateFormat(p.date_format);
    }
  };

  const finish = async () => {
    setBusy(true);
    setError(null);
    try {
      for (const p of people.filter((p) => p.display_name.trim())) {
        await api.post("/identities", {
          display_name: p.display_name.trim(),
          aliases: p.aliases.split(",").map((a) => a.trim()).filter(Boolean),
        });
      }
      await api.post("/onboarding", {
        country: country || null,
        base_currency: currency,
        date_format: dateFormat,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Set up your ledger</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Everything stays on this device. You can change all of this later in Settings.
        </p>
      </div>
      {step === 0 && (
        <Card title="Region & currency">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Country" hint="Only sets sensible defaults.">
              <Select className="w-full" value={country} onChange={(e) => pickCountry(e.target.value)}>
                <option value="">Other / not listed</option>
                {Object.keys(presets).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Base currency" hint="Used for consolidated analytics.">
              <Input value={currency} maxLength={3} placeholder="e.g. EUR" onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
            </Field>
            <Field label="Statement date format" hint="Auto-detects when unambiguous.">
              <Select className="w-full" value={dateFormat} onChange={(e) => setDateFormat(e.target.value)}>
                <option value="auto">Auto-detect</option>
                <option value="DMY">Day / Month / Year</option>
                <option value="MDY">Month / Day / Year</option>
                <option value="YMD">Year / Month / Day</option>
              </Select>
            </Field>
          </div>
          <div className="mt-5 flex justify-end">
            <Button disabled={currency.length !== 3} onClick={() => setStep(1)}>
              Continue
            </Button>
          </div>
        </Card>
      )}
      {step === 1 && (
        <Card title="Who is in your household?">
          <p className="mb-4 text-sm text-fg-muted">
            Names and aliases (as they appear on statements, e.g. initials) are used to work out who owns each account.
          </p>
          <div className="space-y-3">
            {people.map((p, i) => (
              <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
                <Field label="Name">
                  <Input
                    value={p.display_name}
                    onChange={(e) => setPeople(people.map((x, j) => (j === i ? { ...x, display_name: e.target.value } : x)))}
                  />
                </Field>
                <Field label="Aliases (comma separated)">
                  <Input
                    value={p.aliases}
                    onChange={(e) => setPeople(people.map((x, j) => (j === i ? { ...x, aliases: e.target.value } : x)))}
                  />
                </Field>
                <Button variant="ghost" aria-label="Remove" onClick={() => setPeople(people.filter((_, j) => j !== i))}>
                  <Trash2 size={14} />
                </Button>
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => setPeople([...people, { display_name: "", aliases: "" }])}>
            <Plus size={14} /> Add person
          </Button>
          <ErrorNote error={error} />
          <div className="mt-5 flex justify-between">
            <Button variant="ghost" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button disabled={busy} onClick={finish}>
              Finish
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
