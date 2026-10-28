import { cn } from "@/lib/utils";

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-2 flex items-center justify-between text-xs font-bold text-[#434655]">{label}{hint && <span className="font-normal text-[var(--muted)]">{hint}</span>}</span>
      {children}
    </label>
  );
}

export const inputClass = "h-11 w-full rounded-2xl border border-black/[0.08] bg-white px-4 text-sm outline-none transition placeholder:text-[#a4a6b0] focus:border-blue-300 focus:ring-4 focus:ring-blue-100/70";
export const textareaClass = "min-h-28 w-full resize-y rounded-2xl border border-black/[0.08] bg-white px-4 py-3 font-mono text-xs leading-5 outline-none transition placeholder:text-[#a4a6b0] focus:border-blue-300 focus:ring-4 focus:ring-blue-100/70";

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void }) {
  return (
    <div className="grid grid-cols-2 gap-1 rounded-2xl bg-black/[0.04] p-1">
      {options.map((option) => (
        <button key={option.value} type="button" onClick={() => onChange(option.value)} className={cn("h-9 rounded-xl text-xs font-bold transition", value === option.value ? "bg-white text-[var(--ink)] shadow-sm" : "text-[var(--muted)] hover:text-[var(--ink)]")}>{option.label}</button>
      ))}
    </div>
  );
}
