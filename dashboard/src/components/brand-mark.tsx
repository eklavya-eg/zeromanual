import { Eye } from "lucide-react";

import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "brand-mark relative grid size-12 place-items-center overflow-hidden rounded-[17px] text-white",
        className,
      )}
      aria-hidden="true"
    >
      <span className="absolute inset-0 bg-gradient-to-br from-[#6f86ff] via-[#526ff2] to-[#7857db]" />
      <span className="absolute -right-3 -top-3 size-9 rounded-full bg-white/20 blur-md" />
      <Eye className="relative size-[22px]" strokeWidth={2.2} />
      <span className="absolute size-1.5 rounded-full bg-[#b9ffd9] shadow-[0_0_8px_2px_rgba(185,255,217,.55)]" />
    </span>
  );
}
