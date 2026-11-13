import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { categoryPath, useApp } from "../lib/context";
import { money } from "../lib/format";
import { Button, ErrorNote, Field, Input, Modal, Select, cn } from "./ui";

// local calendar date (toISOString would give the UTC date)
const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
};

/** Record a transaction that no statement covers (cash, a transfer from an unimported account…). */
export function AddTransaction({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: () => void }) {
  const { accounts, categories, identities, refresh } = useApp();
  // Imports create accounts in the background; make sure the list is current.
  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);
  const [accountId, setAccountId] = useState<number | "">("");
  const [txnDate, setTxnDate] = useState(today);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [direction, setDirection] = useState<"outflow" | "inflow">("outflow");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [ownerId, setOwnerId] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const account = accounts.find((a) => a.id === accountId) ?? (accounts.length === 1 ? accounts[0] : undefined);
  const value = Number(amount);
  const valid = !!account && !!description.trim() && !!txnDate && Number.isFinite(value) && value > 0;

  const reset = () => {
    setDescription("");
    setAmount("");
    setCategoryId("");
    setError(null);
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid || !account) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/transactions", {
        account_id: account.id,
        txn_date: txnDate,
        description: description.trim(),
        amount: (direction === "outflow" ? -value : value).toFixed(2),
        category_id: categoryId || null,
        owner_identity_id: ownerId || null,
      });
      toast.success("Transaction added", { description: `${description.trim()} · ${money(direction === "outflow" ? -value : value, account.currency)}` });
      reset();
      onAdded();
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add a transaction">
      {accounts.length === 0 ? (
        <p className="text-sm text-fg-muted">Transactions belong to an account. Add one under Accounts → Add account (or import a statement), then come back.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-xs text-fg-muted">For money no imported statement covers, like cash. It&apos;s categorised like any other transaction unless you pick a category.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Account">
              <Select className="w-full" value={account?.id ?? ""} onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : "")} required>
                <option value="">Choose…</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Date">
              <Input type="date" value={txnDate} onChange={(e) => setTxnDate(e.target.value)} required />
            </Field>
          </div>
          <Field label="Description">
            <Input autoFocus value={description} placeholder="e.g. Cash at farmers market" onChange={(e) => setDescription(e.target.value)} required />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={`Amount${account ? ` (${account.currency})` : ""}`}>
              <Input type="number" inputMode="decimal" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required />
            </Field>
            <Field label="Direction">
              <div className="flex h-9 overflow-hidden rounded-md border border-border text-sm">
                {(["outflow", "inflow"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDirection(d)}
                    className={cn("flex-1", direction === d ? "bg-muted font-medium text-fg" : "text-fg-muted hover:bg-muted/50")}
                    aria-pressed={direction === d}
                  >
                    {d === "outflow" ? "Money out" : "Money in"}
                  </button>
                ))}
              </div>
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Category (optional)">
              <Select className="w-full" value={categoryId} onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Classify automatically</option>
                {categories
                  .filter((c) => c.parent_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {categoryPath(categories, c.id)}
                    </option>
                  ))}
              </Select>
            </Field>
            {identities.length > 1 && (
              <Field label="Whose (optional)">
                <Select className="w-full" value={ownerId} onChange={(e) => setOwnerId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">Account owner</option>
                  {identities.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.display_name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
          </div>
          <ErrorNote error={error} />
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || busy}>
              {busy ? "Adding…" : "Add transaction"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
