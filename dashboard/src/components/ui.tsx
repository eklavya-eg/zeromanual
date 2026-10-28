"use client";

import {
  AlertCircle,
  ArrowRight,
  LoaderCircle,
  Plus,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && (
          <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--blue)]">
            {eyebrow}
          </div>
        )}
        <h1 className="text-3xl font-semibold tracking-[-0.04em] sm:text-[38px]">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted)] sm:text-[15px]">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cn("surface", className)}>{children}</section>;
}

export function Button({
  className,
  variant = "primary",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button
      className={cn(
        "inline-flex h-11 items-center justify-center gap-2 rounded-2xl px-4 text-sm font-semibold transition disabled:pointer-events-none disabled:opacity-50",
        variant === "primary" && "bg-[var(--blue)] text-white shadow-lg shadow-blue-500/20 hover:-translate-y-0.5 hover:bg-[#4164ef]",
        variant === "secondary" && "bg-[var(--ink)] text-white shadow-lg shadow-slate-950/10 hover:-translate-y-0.5",
        variant === "ghost" && "border border-black/[0.08] bg-white text-[var(--ink)] hover:bg-black/[0.03]",
        variant === "danger" && "bg-red-50 text-red-700 hover:bg-red-100",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function StatusBadge({ tone = "neutral", children }: { tone?: "success" | "danger" | "info" | "warning" | "neutral"; children: React.ReactNode }) {
  const styles = {
    success: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
    danger: "bg-red-50 text-red-700 ring-red-600/10",
    info: "bg-blue-50 text-blue-700 ring-blue-600/10",
    warning: "bg-amber-50 text-amber-700 ring-amber-600/10",
    neutral: "bg-slate-100 text-slate-600 ring-slate-600/10",
  };
  return <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold capitalize ring-1 ring-inset", styles[tone])}><span className="size-1.5 rounded-full bg-current opacity-70" />{children}</span>;
}

export function MetricCard({ label, value, detail, icon, accent = "blue" }: { label: string; value: string | number; detail: string; icon: React.ReactNode; accent?: "blue" | "peach" | "mint" | "violet" }) {
  const accents = {
    blue: "from-[#e3e9ff] to-[#f7f8ff] text-[#4567ee]",
    peach: "from-[#ffe7d8] to-[#fff9f4] text-[#d56f35]",
    mint: "from-[#dbf4e9] to-[#f6fcf9] text-[#17855c]",
    violet: "from-[#ece3ff] to-[#fbf9ff] text-[#8054d6]",
  };
  return (
    <Card className="group p-5 transition hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(30,31,45,.09)]">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold text-[var(--muted)]">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-0.05em]">{value}</p>
        </div>
        <div className={cn("grid size-11 place-items-center rounded-2xl bg-gradient-to-br", accents[accent])}>{icon}</div>
      </div>
      <p className="mt-4 text-xs text-[var(--muted)]">{detail}</p>
    </Card>
  );
}

export function LoadingState({ label = "Loading workspace" }: { label?: string }) {
  return <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-[var(--muted)]"><LoaderCircle className="size-5 animate-spin text-[var(--blue)]" />{label}</div>;
}

export function ErrorState({ title = "Could not reach Switch", message, compact = false }: { title?: string; message?: string; compact?: boolean }) {
  return (
    <div className={cn("rounded-[22px] border border-red-100 bg-red-50/70 p-5", !compact && "min-h-40 grid place-items-center text-center")}>
      <div>
        <AlertCircle className={cn("size-5 text-red-500", !compact && "mx-auto mb-3 size-7")} />
        <p className="mt-2 text-sm font-bold text-red-800">{title}</p>
        <p className="mt-1 max-w-md text-xs leading-5 text-red-600">{message ?? "Check that the FastAPI service and PostgreSQL are running."}</p>
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, description, action }: { icon: React.ReactNode; title: string; description: string; action?: React.ReactNode }) {
  return (
    <div className="grid min-h-52 place-items-center px-6 text-center">
      <div>
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]">{icon}</div>
        <h3 className="mt-4 text-sm font-bold">{title}</h3>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-[var(--muted)]">{description}</p>
        {action && <div className="mt-4">{action}</div>}
      </div>
    </div>
  );
}

export function Modal({ title, description, open, onClose, children, wide = false }: { title: string; description?: string; open: boolean; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] grid place-items-end bg-[#11131c]/35 p-0 backdrop-blur-sm sm:place-items-center sm:p-6" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className={cn("max-h-[92vh] w-full overflow-y-auto rounded-t-[30px] border border-white/70 bg-[var(--canvas)] p-5 shadow-2xl sm:rounded-[30px] sm:p-7", wide ? "max-w-6xl" : "max-w-xl")} onMouseDown={(event) => event.stopPropagation()}>
        <div className="mb-6 flex items-start justify-between gap-4">
          <div><h2 className="text-xl font-semibold tracking-[-0.03em]">{title}</h2>{description && <p className="mt-1 text-sm text-[var(--muted)]">{description}</p>}</div>
          <button onClick={onClose} className="grid size-9 place-items-center rounded-xl border border-black/[0.07] bg-white" aria-label="Close"><X className="size-4" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function AddButton({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <Button {...props}><Plus className="size-4" />{children}</Button>;
}

export function InlineLink({ children }: { children: React.ReactNode }) {
  return <span className="inline-flex items-center gap-1 font-semibold text-[var(--blue)]">{children}<ArrowRight className="size-3" /></span>;
}
