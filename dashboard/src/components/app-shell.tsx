"use client";

import {
  Activity,
  Bot,
  CalendarClock,
  ChartNoAxesCombined,
  Command,
  GitBranch,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/utils";

const navigation = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/workflows", label: "Workflows", icon: GitBranch },
  { href: "/schedules", label: "Schedules", icon: CalendarClock },
  { href: "/agents", label: "Sub-agents", icon: Bot },
  { href: "/runs", label: "Runs", icon: Activity },
  { href: "/usage", label: "Usage", icon: ChartNoAxesCombined },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");

  function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!search.trim()) return;
    router.push(`/workflows?q=${encodeURIComponent(search.trim())}`);
  }

  return (
    <div className="min-h-screen bg-[var(--canvas)] text-[var(--ink)]">
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />

      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[92px] border-r border-black/[0.06] bg-white/70 backdrop-blur-xl lg:flex lg:flex-col lg:items-center">
        <Link
          href="/"
          className="mt-6 grid size-12 place-items-center rounded-2xl bg-[var(--ink)] text-white shadow-lg shadow-indigo-950/15"
          aria-label="Switch overview"
        >
          <Sparkles className="size-5" />
        </Link>
        <nav className="mt-10 flex flex-1 flex-col gap-2" aria-label="Primary navigation">
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-label={item.label}
                className={cn(
                  "group relative grid size-12 place-items-center rounded-2xl text-[var(--muted)] transition-all hover:bg-black/[0.04] hover:text-[var(--ink)]",
                  active && "bg-[var(--blue)] text-white shadow-lg shadow-blue-500/25 hover:bg-[var(--blue)] hover:text-white",
                )}
              >
                <item.icon className="size-[19px]" strokeWidth={active ? 2.3 : 1.8} />
                <span className="pointer-events-none absolute left-14 z-50 whitespace-nowrap rounded-lg bg-[var(--ink)] px-2.5 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                  {item.label}
                </span>
              </Link>
            );
          })}
        </nav>
        <div className="mb-6 grid size-10 place-items-center rounded-full bg-gradient-to-br from-[#d8deff] to-[#ffd8c3] text-sm font-bold text-[#2d3150]">
          S
        </div>
      </aside>

      <header className="fixed inset-x-0 top-0 z-30 h-[78px] border-b border-black/[0.06] bg-[var(--canvas)]/80 backdrop-blur-xl lg:left-[92px]">
        <div className="flex h-full items-center gap-3 px-4 sm:px-6 lg:px-9">
          <button
            className="grid size-10 place-items-center rounded-xl border border-black/[0.07] bg-white lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
          <form onSubmit={submitSearch} className="relative max-w-xl flex-1">
            <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search workflows, agents, runs…"
              className="h-11 w-full rounded-2xl border border-black/[0.07] bg-white/80 pl-11 pr-20 text-sm outline-none transition focus:border-blue-300 focus:ring-4 focus:ring-blue-100/70"
            />
            <span className="absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-1 rounded-lg border border-black/[0.07] bg-[#f7f7f5] px-2 py-1 font-mono text-[10px] text-[var(--muted)] sm:flex">
              <Command className="size-3" /> K
            </span>
          </form>
          <div className="hidden items-center gap-2 rounded-full border border-emerald-200/70 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 sm:flex">
            <span className="size-2 rounded-full bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,.12)]" />
            Local environment
          </div>
          <Link
            href="/workflows?new=true"
            className="hidden h-11 items-center gap-2 rounded-2xl bg-[var(--ink)] px-4 text-sm font-semibold text-white shadow-lg shadow-slate-950/10 transition hover:-translate-y-0.5 md:flex"
          >
            <Sparkles className="size-4" />
            Create workflow
          </Link>
        </div>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)}>
          <aside className="h-full w-[290px] bg-white p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 font-bold">
                <span className="grid size-10 place-items-center rounded-2xl bg-[var(--ink)] text-white"><Sparkles className="size-4" /></span>
                Switch
              </div>
              <button className="grid size-9 place-items-center rounded-xl bg-black/[0.04]" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-4" /></button>
            </div>
            <nav className="mt-8 space-y-1">
              {navigation.map((item) => (
                <Link key={item.href} href={item.href} onClick={() => setMobileOpen(false)} className={cn("flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium text-[var(--muted)]", (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)) && "bg-blue-50 text-[var(--blue)]")}>
                  <item.icon className="size-[18px]" /> {item.label}
                </Link>
              ))}
            </nav>
          </aside>
        </div>
      )}

      <main className="relative min-h-screen pt-[78px] lg:pl-[92px]">
        <div className="mx-auto w-full max-w-[1680px] p-4 pb-24 sm:p-6 lg:p-9 lg:pb-10">
          {children}
        </div>
      </main>

      <nav className="fixed inset-x-3 bottom-3 z-40 flex justify-around rounded-[22px] border border-black/[0.07] bg-white/90 p-2 shadow-[0_16px_50px_rgba(25,25,35,.18)] backdrop-blur-xl lg:hidden" aria-label="Mobile navigation">
        {navigation.slice(0, 5).map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} aria-label={item.label} className={cn("grid size-11 place-items-center rounded-2xl text-[var(--muted)]", active && "bg-[var(--blue)] text-white")}>
              <item.icon className="size-[18px]" />
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
