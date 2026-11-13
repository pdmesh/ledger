// Small shadcn-style primitives built on Tailwind (no runtime UI dependency).
import clsx from "clsx";
import { CircleHelp, X } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, RefObject, SelectHTMLAttributes } from "react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GLOSSARY, type GlossaryKey } from "../lib/glossary";

export const cn = clsx;

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
        variant === "primary" && "bg-accent text-accent-fg hover:bg-accent/90",
        variant === "secondary" && "bg-muted text-fg hover:bg-muted/70",
        variant === "outline" && "border border-border bg-surface hover:bg-muted",
        variant === "ghost" && "hover:bg-muted text-fg-muted hover:text-fg",
        variant === "danger" && "bg-negative text-white hover:bg-negative/90",
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, children, title, actions }: { className?: string; children: ReactNode; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={cn("rounded-lg border border-border bg-surface", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <h3 className="text-sm font-semibold">{title}</h3>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "positive" | "negative" | "warning" | "accent"; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium",
        tone === "neutral" && "bg-muted text-fg-muted",
        tone === "positive" && "bg-positive/12 text-positive",
        tone === "negative" && "bg-negative/12 text-negative",
        tone === "warning" && "bg-warning/15 text-warning",
        tone === "accent" && "bg-accent/12 text-accent",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-border bg-surface px-2.5 text-sm placeholder:text-fg-subtle",
        "focus:outline-2 focus:outline-accent",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 appearance-none rounded-md border border-border bg-surface bg-[length:14px] bg-[position:right_0.5rem_center] bg-no-repeat pl-2.5 pr-8 text-sm focus:outline-2 focus:outline-accent",
        "bg-[image:var(--select-chevron)]",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Field({ label, hint, help, children }: { label: string; hint?: ReactNode; help?: GlossaryKey; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="flex items-center gap-1 text-xs font-medium text-fg-muted">
        {label}
        {help && <Help term={help} />}
      </span>
      {children}
      {hint && <span className="block text-[11px] text-fg-subtle">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn("relative h-5 w-9 rounded-full transition-colors", checked ? "bg-accent" : "bg-border")}
      >
        <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all", checked ? "left-4.5" : "left-0.5")} />
      </button>
      {label}
    </label>
  );
}

export function Drawer({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className={cn("flex h-full w-full flex-col border-l border-border bg-bg shadow-xl", wide ? "max-w-3xl" : "max-w-xl")}
        onClick={(e) => {
          // don't toggle a surrounding <label>'s control or open a clickable row
          e.preventDefault();
          e.stopPropagation();
        }}
      >
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="truncate text-base font-semibold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-lg border border-border bg-bg shadow-xl" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </Button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------------------
// In-app confirmation. window.confirm() is not reliably shown inside the desktop webview
// (it can return false without asking), so destructive actions use this instead.
// --------------------------------------------------------------------------------------

interface ConfirmRequest {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  resolve: (ok: boolean) => void;
}

let showConfirm: ((r: ConfirmRequest) => void) | null = null;

/** Ask the user to confirm; resolves true only if they press the confirm button. */
export function confirmAction(opts: Omit<ConfirmRequest, "resolve">): Promise<boolean> {
  return new Promise((resolve) => {
    if (!showConfirm) return resolve(false);
    showConfirm({ ...opts, resolve });
  });
}

/** Mount once near the app root. */
export function ConfirmHost() {
  const [req, setReq] = useState<ConfirmRequest | null>(null);
  useEffect(() => {
    showConfirm = (r) => setReq(r);
    return () => {
      showConfirm = null;
    };
  }, []);
  const done = (ok: boolean) => {
    req?.resolve(ok);
    setReq(null);
  };
  useEffect(() => {
    if (!req) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && done(false);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });
  return (
    <Modal open={!!req} onClose={() => done(false)} title={req?.title ?? ""}>
      {req?.body && <div className="mb-5 text-sm text-fg-muted">{req.body}</div>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => done(false)}>
          Cancel
        </Button>
        <Button autoFocus variant={req?.danger ? "danger" : "primary"} onClick={() => done(true)}>
          {req?.confirmLabel ?? "Confirm"}
        </Button>
      </div>
    </Modal>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-fg-muted">{children}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string }[] }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-border">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-sm",
            value === it.value ? "border-accent font-medium text-fg" : "border-transparent text-fg-muted hover:text-fg",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function ErrorNote({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return <p className="rounded-md bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>;
}

export function Confidence({ value, method }: { value: number | null; method: string | null }) {
  const how = method && method in GLOSSARY ? GLOSSARY[method as GlossaryKey] : null;
  if (method === "user")
    return (
      <Term term="user">
        <Badge tone="accent">You</Badge>
      </Term>
    );
  if (value === null || value === undefined) return <Badge>—</Badge>;
  const tone = value >= 0.8 ? "positive" : value >= 0.5 ? "warning" : "negative";
  return (
    <Term
      text={
        <>
          {Math.round(value * 100)}% confidence in this category.{how ? ` ${how}` : ""}
        </>
      }
    >
      <Badge tone={tone} className="tabular-nums">
        {Math.round(value * 100)}%
      </Badge>
    </Term>
  );
}

// --------------------------------------------------------------------------------------
// Help tooltips. Rendered in a portal with fixed positioning so scrolling tables and
// cards never clip them. Shown on hover and on keyboard focus.
// --------------------------------------------------------------------------------------

function useTooltip() {
  const ref = useRef<HTMLElement | null>(null);
  const id = useId();
  const [pos, setPos] = useState<{ x: number; y: number; below: boolean } | null>(null);
  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const below = r.top < 120;
    setPos({ x: Math.min(Math.max(r.left + r.width / 2, 150), window.innerWidth - 150), y: below ? r.bottom + 6 : r.top - 6, below });
  };
  const hide = () => setPos(null);
  return { ref, id, pos, handlers: { onMouseEnter: show, onMouseLeave: hide, onFocus: show, onBlur: hide } };
}

function TooltipBubble({ id, pos, text }: { id: string; pos: { x: number; y: number; below: boolean }; text: ReactNode }) {
  return createPortal(
    <div
      id={id}
      role="tooltip"
      className="pointer-events-none fixed z-[60] w-max max-w-[280px] rounded-md border border-border bg-surface px-2.5 py-1.5 text-left text-xs font-normal normal-case leading-snug tracking-normal text-fg shadow-lg"
      style={{ left: pos.x, top: pos.y, transform: `translate(-50%, ${pos.below ? "0" : "-100%"})` }}
    >
      {text}
    </div>,
    document.body,
  );
}

const helpText = (term?: GlossaryKey, text?: ReactNode) => text ?? (term ? GLOSSARY[term] : null);

/** A small “?” that explains the thing next to it. */
export function Help({ term, text, className }: { term?: GlossaryKey; text?: ReactNode; className?: string }) {
  const t = useTooltip();
  const body = helpText(term, text);
  if (!body) return null;
  return (
    <>
      <span
        ref={t.ref as RefObject<HTMLSpanElement>}
        tabIndex={0}
        role="button"
        aria-label="Help"
        aria-describedby={t.pos ? t.id : undefined}
        className={cn("inline-flex cursor-help align-middle text-fg-subtle hover:text-fg-muted focus:text-fg-muted focus:outline-none", className)}
        onClick={(e) => e.stopPropagation()}
        {...t.handlers}
      >
        <CircleHelp size={12} />
      </span>
      {t.pos && <TooltipBubble id={t.id} pos={t.pos} text={body} />}
    </>
  );
}

/** Wrap a label or badge so hovering it explains it (dotted underline hints at that). */
export function Term({ term, text, children, className }: { term?: GlossaryKey; text?: ReactNode; children: ReactNode; className?: string }) {
  const t = useTooltip();
  const body = helpText(term, text);
  if (!body) return <>{children}</>;
  return (
    <>
      <span
        ref={t.ref as RefObject<HTMLSpanElement>}
        tabIndex={0}
        aria-describedby={t.pos ? t.id : undefined}
        className={cn("cursor-help decoration-fg-subtle/60 decoration-dotted underline-offset-2 hover:underline focus:underline focus:outline-none", className)}
        {...t.handlers}
      >
        {children}
      </span>
      {t.pos && <TooltipBubble id={t.id} pos={t.pos} text={body} />}
    </>
  );
}
