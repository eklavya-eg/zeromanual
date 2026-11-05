"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Clock3, Cpu, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { inputClass } from "@/components/form-fields";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function WorkersPage() {
  const [search, setSearch] = useState("");
  const workersQuery = useQuery({
    queryKey: ["workers"],
    queryFn: api.workers.list,
    refetchInterval: 15_000,
  });
  const workers = workersQuery.data ?? [];
  const filtered = workers.filter((worker) =>
    `${worker.name} ${worker.id}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div>
      <PageHeader
        eyebrow="Background operations"
        title="Workers"
        description="Inspect registered Celery workers, task outcomes, and the steps behind every execution."
        action={<StatusBadge tone="info">Refreshes every 15s</StatusBadge>}
      />
      <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" />
          <input
            aria-label="Search workers"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search workers by name or ID"
            className={`${inputClass} pl-11`}
          />
        </div>
        <p className="text-xs text-[var(--muted)]">{workers.length} registered · {workers.filter((worker) => worker.enabled).length} enabled</p>
      </div>
      {workersQuery.isLoading ? <LoadingState label="Loading workers" /> : workersQuery.isError ? (
        <ErrorState title="Workers unavailable" message={workersQuery.error.message} />
      ) : filtered.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((worker) => (
            <Link key={worker.id} href={`/workers/${worker.id}`} className="group block rounded-[24px] outline-offset-4" aria-label={`Open ${worker.name} dashboard`}>
              <Card className="h-full p-5 group-hover:-translate-y-1 group-hover:border-blue-300/50">
                <div className="flex items-center justify-between gap-3">
                  <div className="grid size-12 place-items-center rounded-2xl bg-[var(--soft)] text-[var(--blue)]"><Cpu className="size-6" /></div>
                  <StatusBadge tone={worker.enabled ? "success" : "neutral"}>{worker.enabled ? "Enabled" : "Disabled"}</StatusBadge>
                </div>
                <h2 className="mt-5 break-words text-lg font-semibold tracking-tight">{worker.name}</h2>
                <p className="mt-2 break-all font-mono text-[10px] text-[var(--muted)]">{worker.id}</p>
                <div className="mt-5 flex items-center gap-2 text-xs text-[var(--muted)]"><Clock3 className="size-3.5" />Registered {formatDateTime(worker.created_at)}</div>
                <div className="mt-5 flex items-center justify-between border-t border-[var(--line)] pt-4 text-xs font-semibold text-[var(--blue)]">
                  View worker dashboard<ArrowUpRight className="size-4 transition group-hover:translate-x-0.5" />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <Card><EmptyState icon={<Cpu className="size-5" />} title={workers.length ? "No matching workers" : "No workers registered yet"} description={workers.length ? "Try another name or worker ID." : "Workers register when their first task starts. Task history and logs will appear here automatically."} /></Card>
      )}
      <p className="mt-5 text-xs leading-5 text-[var(--muted)]">Enabled reflects worker registration, not a live Celery heartbeat. Open a worker to inspect running and completed tasks.</p>
    </div>
  );
}
