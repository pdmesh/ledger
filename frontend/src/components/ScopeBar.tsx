import { useApp, type RangePreset } from "../lib/context";
import { Input, Select } from "./ui";

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "3m", label: "Last 3 months" },
  { value: "6m", label: "Last 6 months" },
  { value: "12m", label: "Last 12 months" },
  { value: "ytd", label: "Year to date" },
  { value: "all", label: "All time" },
  { value: "custom", label: "Custom…" },
];

/** Global view selector: whose finances (household / person / joint) and which period. */
export function ScopeBar() {
  const { view, setView, identities } = useApp();
  const who =
    view.scope === "household" ? "household" : view.scope === "joint" ? "joint" : `person:${view.identityId ?? ""}`;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-6 py-2.5">
      <Select
        aria-label="Whose finances"
        value={who}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "household" || v === "joint") setView({ ...view, scope: v, identityId: undefined });
          else setView({ ...view, scope: "individual", identityId: Number(v.split(":")[1]) });
        }}
      >
        <option value="household">Entire household</option>
        {identities.map((i) => (
          <option key={i.id} value={`person:${i.id}`}>
            {i.display_name}
          </option>
        ))}
        {identities.length > 1 && <option value="joint">Joint accounts</option>}
      </Select>
      <Select
        aria-label="Period"
        value={view.preset}
        onChange={(e) => setView({ ...view, preset: e.target.value as RangePreset })}
      >
        {PRESETS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </Select>
      {view.preset === "custom" && (
        <>
          <Input type="date" className="w-40" value={view.from ?? ""} onChange={(e) => setView({ ...view, from: e.target.value })} />
          <span className="text-fg-subtle">to</span>
          <Input type="date" className="w-40" value={view.to ?? ""} onChange={(e) => setView({ ...view, to: e.target.value })} />
        </>
      )}
    </div>
  );
}
