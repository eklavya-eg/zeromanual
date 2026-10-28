"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Database, ExternalLink, Globe2, HardDrive, Moon, Network, ServerCog } from "lucide-react";

import { Card, PageHeader, StatusBadge } from "@/components/ui";
import { API_BASE_URL, api } from "@/lib/api";

export default function SettingsPage() {
  const healthQuery = useQuery({ queryKey: ["agents"], queryFn: api.agents.list, retry: 0 });
  return (
    <div>
      <PageHeader eyebrow="Workspace" title="Settings" description="Environment configuration and local infrastructure status." />
      <div className="grid gap-5 xl:grid-cols-[1fr_.72fr]">
        <Card className="p-6"><div className="flex items-start justify-between"><div><h2 className="text-sm font-bold">Switch API</h2><p className="mt-1 text-xs text-[var(--muted)]">Dashboard data source</p></div><StatusBadge tone={healthQuery.isSuccess ? "success" : healthQuery.isLoading ? "warning" : "danger"}>{healthQuery.isSuccess ? "Connected" : healthQuery.isLoading ? "Checking" : "Offline"}</StatusBadge></div><div className="mt-5 flex items-center gap-3 rounded-2xl border border-black/[0.06] bg-white p-4"><div className="grid size-10 place-items-center rounded-xl bg-blue-50 text-[var(--blue)]"><Globe2 className="size-4" /></div><div className="min-w-0 flex-1"><p className="text-xs font-bold">Base URL</p><p className="mt-1 truncate font-mono text-[11px] text-[var(--muted)]">{API_BASE_URL}</p></div><a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer" className="grid size-9 place-items-center rounded-xl border border-black/[0.07] bg-white" aria-label="Open API documentation"><ExternalLink className="size-4" /></a></div><p className="mt-4 text-xs leading-5 text-[var(--muted)]">Set <code className="rounded bg-black/[0.04] px-1.5 py-1 font-mono">NEXT_PUBLIC_SWITCH_API_URL</code> before building the dashboard to change this address.</p></Card>
        <Card className="p-6"><div className="grid size-11 place-items-center rounded-2xl bg-[var(--ink)] text-white"><Moon className="size-5" /></div><h2 className="mt-5 text-lg font-semibold">Appearance</h2><p className="mt-2 text-sm leading-6 text-[var(--muted)]">The warm light operations theme is active. Dark theme will be added after the primary workflows are validated.</p><div className="mt-5 rounded-2xl bg-gradient-to-r from-[#dbe2ff] via-[#f5efff] to-[#ffe2d0] p-4 text-xs font-bold text-[#4d5269]">Original Switch visual system</div></Card>
      </div>
      <Card className="mt-5 p-6"><div className="mb-5"><h2 className="text-sm font-bold">Local infrastructure</h2><p className="mt-1 text-xs text-[var(--muted)]">Expected services from the repository Compose stack</p></div><div className="grid gap-3 md:grid-cols-3"><Infrastructure icon={<Database className="size-4" />} name="PostgreSQL" detail="Prisma persistence · port 5432" /><Infrastructure icon={<Network className="size-4" />} name="switch-backend" detail="Private Compose network" /><Infrastructure icon={<HardDrive className="size-4" />} name="Postgres volume" detail="switch-postgres-data" /></div></Card>
      <Card className="mt-5 p-6"><div className="flex items-center gap-3"><div className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600"><ServerCog className="size-4" /></div><div><h2 className="text-sm font-bold">Runtime model</h2><p className="mt-1 text-xs text-[var(--muted)]">FastAPI + Prisma + Windows Task Scheduler</p></div></div><div className="mt-5 grid gap-3 sm:grid-cols-3">{["Async Prisma client", "Startup reconciliation", "Windows callback triggers"].map((item) => <div key={item} className="flex items-center gap-2 rounded-2xl bg-black/[0.025] px-4 py-3 text-xs"><CheckCircle2 className="size-4 text-emerald-600" />{item}</div>)}</div></Card>
    </div>
  );
}

function Infrastructure({ icon, name, detail }: { icon: React.ReactNode; name: string; detail: string }) {
  return <div className="flex items-center gap-3 rounded-2xl border border-black/[0.06] bg-white p-4"><div className="grid size-9 place-items-center rounded-xl bg-black/[0.035] text-[var(--muted)]">{icon}</div><div><p className="text-xs font-bold">{name}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{detail}</p></div></div>;
}
