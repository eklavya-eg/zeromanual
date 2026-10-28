"use client";

import { useQueries } from "@tanstack/react-query";
import { Activity, ArrowRight, CheckCircle2, CircleDashed, Clock3, Filter, Search, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { inputClass } from "@/components/form-fields";
import { QueryAlert } from "@/components/query-alert";
import { Card, EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, formatDuration, runTone, shortId } from "@/lib/utils";

export default function RunsPage() {
  const [runsQuery, workflowsQuery] = useQueries({ queries: [
    { queryKey: ["runs"], queryFn: () => api.runs.list(), refetchInterval: 15_000 },
    { queryKey: ["workflows"], queryFn: api.workflows.list },
  ] });
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const workflows = useMemo(() => workflowsQuery.data ?? [], [workflowsQuery.data]);
  const filtered = useMemo(() => runs.filter((run) => {
    const workflow = workflows.find((item) => item.id === run.workflow_id);
    return (status === "all" || run.status === status) && `${run.id} ${workflow?.name ?? ""}`.toLowerCase().includes(search.toLowerCase());
  }), [runs, workflows, search, status]);

  return (
    <div>
      <PageHeader eyebrow="Execution history" title="Runs" description="Follow every workflow occurrence from trigger to individual sub-agent result." />
      <QueryAlert show={runsQuery.isError || workflowsQuery.isError} />
      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Activity className="size-5" /></div><div><p className="text-2xl font-semibold">{runs.length}</p><p className="text-xs text-[var(--muted)]">Total executions</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-600"><CheckCircle2 className="size-5" /></div><div><p className="text-2xl font-semibold">{runs.filter((run) => run.status === "succeeded").length}</p><p className="text-xs text-[var(--muted)]">Succeeded</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-red-50 text-red-600"><TriangleAlert className="size-5" /></div><div><p className="text-2xl font-semibold">{runs.filter((run) => run.status === "failed").length}</p><p className="text-xs text-[var(--muted)]">Need attention</p></div></Card>
      </div>
      <Card className="overflow-hidden p-0">
        <div className="flex flex-col gap-3 border-b border-black/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative max-w-md flex-1"><Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" /><input value={search} onChange={(event) => setSearch(event.target.value)} className={`${inputClass} pl-11`} placeholder="Search workflow or run ID" /></div>
          <div className="flex items-center gap-2"><Filter className="size-4 text-[var(--muted)]" /><select value={status} onChange={(event) => setStatus(event.target.value)} className="h-10 rounded-xl border border-black/[0.07] bg-white px-3 text-xs font-semibold outline-none"><option value="all">All statuses</option><option value="running">Running</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option></select></div>
        </div>
        {filtered.length ? <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left"><thead><tr className="border-b border-black/[0.06] text-[10px] font-bold uppercase tracking-wider text-[var(--muted)]"><th className="px-6 py-4">Workflow</th><th className="px-4 py-4">Status</th><th className="px-4 py-4">Trigger</th><th className="px-4 py-4">Started</th><th className="px-4 py-4">Duration</th><th className="px-4 py-4">Attempts</th><th className="px-6 py-4" /></tr></thead><tbody className="divide-y divide-black/[0.05]">{filtered.map((run) => { const workflow = workflows.find((item) => item.id === run.workflow_id); return <tr key={run.id} className="group transition hover:bg-black/[0.018]"><td className="px-6 py-4"><div className="flex items-center gap-3"><div className="grid size-9 place-items-center rounded-xl bg-black/[0.035] text-[var(--muted)]">{run.status === "running" ? <CircleDashed className="size-4 animate-spin" /> : <Activity className="size-4" />}</div><div><p className="text-sm font-semibold">{workflow?.name ?? "Unknown workflow"}</p><p className="mt-0.5 font-mono text-[10px] text-[var(--muted)]">{shortId(run.id)}</p></div></div></td><td className="px-4 py-4"><StatusBadge tone={runTone(run.status)}>{run.status}</StatusBadge></td><td className="px-4 py-4 text-xs text-[var(--muted)]">{run.schedule_id ? "Schedule" : "Manual"}</td><td className="px-4 py-4 text-xs text-[var(--muted)]">{formatDateTime(run.started_at)}</td><td className="px-4 py-4 text-xs font-semibold"><span className="inline-flex items-center gap-1.5"><Clock3 className="size-3.5 text-[var(--muted)]" />{formatDuration(run)}</span></td><td className="px-4 py-4 text-xs">{run.attempt_count}</td><td className="px-6 py-4 text-right"><Link href={`/runs/${run.id}`} className="inline-grid size-9 place-items-center rounded-xl border border-black/[0.07] bg-white text-[var(--muted)] transition group-hover:text-[var(--blue)]" aria-label="Open run"><ArrowRight className="size-4" /></Link></td></tr>; })}</tbody></table></div> : <EmptyState icon={<Activity className="size-5" />} title="No runs found" description="Execution history appears after a workflow runs manually or from a schedule." />}
      </Card>
    </div>
  );
}
