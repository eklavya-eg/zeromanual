"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowLeft, CheckCircle2, ChevronLeft, ChevronRight, Clock3, ExternalLink, ListChecks, Percent, SkipForward, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";

import { inputClass } from "@/components/form-fields";
import { Button, Card, EmptyState, ErrorState, LoadingState, MetricCard, PageHeader, StatusBadge } from "@/components/ui";
import { WorkerTaskDetail } from "@/components/worker-task-detail";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, runTone, shortId } from "@/lib/utils";

export default function WorkerDashboardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const dashboardQuery = useQuery({
    queryKey: ["worker-dashboard", id, status, page],
    queryFn: () => api.workers.dashboard(id, page, status),
    refetchInterval: 10_000,
    retry: (attempt, error) => !(error instanceof ApiError && [404, 422].includes(error.status)) && attempt < 1,
  });
  const backLink = <Link href="/workers" className="mb-5 inline-flex items-center gap-2 text-xs font-semibold text-[var(--muted)] hover:text-[var(--ink)]"><ArrowLeft className="size-4" />Back to workers</Link>;

  if (dashboardQuery.isLoading) return <div>{backLink}<LoadingState label="Loading worker dashboard" /></div>;
  if (dashboardQuery.isError || !dashboardQuery.data) {
    const missing = dashboardQuery.error instanceof ApiError && dashboardQuery.error.status === 404;
    return <div>{backLink}<ErrorState title={missing ? "Worker not found" : "Worker dashboard unavailable"} message={dashboardQuery.error?.message} /></div>;
  }

  const { worker, metrics, runs, total, page_size } = dashboardQuery.data;
  const totalPages = Math.max(1, Math.ceil(total / page_size));

  return (
    <div>
      {backLink}
      <PageHeader
        eyebrow="Worker observability"
        title={worker.name}
        description={`Registered ${formatDateTime(worker.created_at)} · Refreshes every 10 seconds`}
        action={<StatusBadge tone={worker.enabled ? "success" : "neutral"}>{worker.enabled ? "Enabled" : "Disabled"}</StatusBadge>}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <MetricCard label="Total tasks" value={metrics.total_runs} detail="All recorded executions" icon={<ListChecks className="size-5" />} />
        <MetricCard label="Running" value={metrics.running} detail="Tasks currently marked running" icon={<Activity className="size-5" />} accent="violet" />
        <MetricCard label="Succeeded" value={metrics.succeeded} detail="Completed successfully" icon={<CheckCircle2 className="size-5" />} accent="mint" />
        <MetricCard label="Failed" value={metrics.failed} detail="Terminal task failures" icon={<TriangleAlert className="size-5" />} accent="peach" />
        <MetricCard label="Skipped" value={metrics.skipped} detail="Duplicates and red-flag jobs" icon={<SkipForward className="size-5" />} accent="violet" />
        <MetricCard label="Success rate" value={metrics.success_rate === null ? "—" : `${metrics.success_rate}%`} detail="Of succeeded and failed tasks" icon={<Percent className="size-5" />} accent="mint" />
      </div>
      <Card className="mt-6 overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-[var(--line)] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div><h2 className="text-sm font-bold">Task history</h2><p className="mt-1 text-xs text-[var(--muted)]">Open a task to inspect its payload, result, and step logs.</p></div>
          <select
            aria-label="Filter tasks by status"
            className={`${inputClass} sm:w-44`}
            value={status}
            onChange={(event) => { setStatus(event.target.value); setPage(1); }}
          >
            <option value="">All statuses</option>
            <option value="running">Running</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="skipped">Skipped</option>
          </select>
        </div>
        {runs.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1180px] text-left text-xs">
              <thead className="bg-[var(--soft)] text-[var(--muted)]"><tr>{["Task", "Status", "Company", "Job title", "Package (INR)", "Platform", "Job URL", "Started", "Failed step", "Duration"].map((label) => <th key={label} scope="col" className="px-5 py-3 font-semibold">{label}</th>)}</tr></thead>
              <tbody>
                {runs.map((run) => {
                  const duration = run.finished_at ? Math.max(0, Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1_000)) : null;
                  return (
                    <tr key={run.id} className="border-t border-[var(--line)] transition hover:bg-[var(--soft)]">
                      <td className="px-5 py-4"><button onClick={() => setSelectedRun(run.id)} className="whitespace-nowrap font-mono font-semibold text-[var(--blue)] underline-offset-4 hover:underline" aria-label={`View task ${run.id}`}>{shortId(run.celery_task_id)}</button></td>
                      <td className="px-5 py-4"><StatusBadge tone={runTone(run.status)}>{run.status}</StatusBadge></td>
                      <td className="min-w-32 max-w-48 break-words px-5 py-4 font-semibold">{run.company_name || "NA"}</td>
                      <td className="min-w-40 max-w-56 break-words px-5 py-4">{run.job_title || "NA"}</td>
                      <td className="min-w-28 max-w-44 break-words px-5 py-4">{run.package || "NA"}</td>
                      <td className="px-5 py-4">{run.platform || "NA"}</td>
                      <td className="max-w-56 px-5 py-4">{/^https?:\/\//i.test(run.job_url) ? <a href={run.job_url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-[var(--muted)] hover:text-[var(--blue)]" title={run.job_url}><span className="max-w-44 truncate">{run.job_url}</span><ExternalLink className="size-3 shrink-0" /></a> : <span className="break-all">{run.job_url}</span>}</td>
                      <td className="whitespace-nowrap px-5 py-4 text-[var(--muted)]">{formatDateTime(run.started_at)}</td>
                      <td className="px-5 py-4 font-mono">{run.step_failed ?? "—"}</td>
                      <td className="whitespace-nowrap px-5 py-4 text-[var(--muted)]">{duration !== null ? `${duration}s` : run.status === "running" ? "In progress" : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <EmptyState icon={<Clock3 className="size-5" />} title={status ? "No tasks with this status" : "No tasks on this page"} description="Task executions will appear here when this worker processes a job." />}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] p-5">
          <p className="text-xs text-[var(--muted)]">{total} matching tasks · Page {page} of {totalPages}</p>
          <div className="flex gap-2"><Button variant="ghost" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}><ChevronLeft className="size-4" />Previous</Button><Button variant="ghost" onClick={() => setPage((current) => current + 1)} disabled={page >= totalPages}>Next<ChevronRight className="size-4" /></Button></div>
        </div>
      </Card>
      <p className="mt-4 break-all font-mono text-[10px] text-[var(--muted)]">Worker ID: {worker.id}</p>
      {selectedRun && <WorkerTaskDetail runId={selectedRun} onClose={() => setSelectedRun(null)} />}
    </div>
  );
}
