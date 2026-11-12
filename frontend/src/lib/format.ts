let baseCurrency = "USD";
let locale: string | undefined;

export function configureFormat(currency: string | null | undefined, loc?: string) {
  if (currency) baseCurrency = currency;
  locale = loc || undefined;
}

export function money(v: string | number | null | undefined, currency = baseCurrency, compact = false) {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency && currency.length === 3 && currency !== "XXX" ? currency : baseCurrency,
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 1 : 2,
    }).format(n);
  } catch {
    return n.toFixed(2);
  }
}

export function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === "") return 0;
  return typeof v === "number" ? v : Number(v);
}

export function pct(v: string | number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return `${(num(v) * 100).toFixed(1)}%`;
}

export function date(d: string | null | undefined) {
  if (!d) return "—";
  const dt = new Date(d.length === 10 ? `${d}T00:00:00` : d);
  return dt.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
}

export function bytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function humanize(s: string | null | undefined) {
  if (!s) return "—";
  return s.replace(/[_-]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function isoDate(d: Date) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}
