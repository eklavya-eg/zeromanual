"use client";

import { WifiOff } from "lucide-react";

export function QueryAlert({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="mb-6 flex items-start gap-3 rounded-[20px] border border-amber-200/70 bg-amber-50/80 px-4 py-3 text-xs text-amber-800">
      <WifiOff className="mt-0.5 size-4 shrink-0" />
      <div><span className="font-bold">Live data is unavailable.</span> The dashboard shell remains usable; start Switch and PostgreSQL to load operational data.</div>
    </div>
  );
}
