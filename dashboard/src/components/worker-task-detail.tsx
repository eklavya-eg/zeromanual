"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock3, FileText, TriangleAlert } from "lucide-react";

import { ErrorState, LoadingState, Modal, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, runTone, shortId } from "@/lib/utils";

function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> | null }) {
  return (
    <section className="min-w-0">
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-[var(--muted)]">{title}</h3>
      <pre className="scrollbar-thin max-h-80 overflow-auto rounded-2xl border border-[var(--line)] bg-[var(--soft)] p-4 text-xs leading-6 text-[var(--ink)]">{value === null ? "No result recorded yet." : JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

export function WorkerTaskDetail({ runId, onClose }: { runId: string; onClose: () => void }) {
  const runQuery = useQuery({
    queryKey: ["worker-run", runId],
    queryFn: () => api.workers.run(runId),
    refetchInterval: 10_000,
  });
  const logsQuery = useQuery({
    queryKey: ["worker-run-logs", runId],
    queryFn: () => api.workers.logs(runId),
    refetchInterval: 10_000,
  });
  const skipQuery = useQuery({
    queryKey: ["worker-run-skip", runId],
    queryFn: () => api.workers.skip(runId),
    enabled: runQuery.data?.status === "skipped",
  });
  const run = runQuery.data;
  const logs = logsQuery.data ?? [];

  return (
    <Modal open onClose={onClose} title={`Task ${shortId(runId)}`} description="Execution state, input, output, and flushed step logs." wide>
      {runQuery.isLoading ? <LoadingState label="Loading worker task" /> : runQuery.isError || !run ? (
        <ErrorState title="Task unavailable" message={runQuery.error?.message} />
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge tone={runTone(run.status)}>{run.status}</StatusBadge>
            <span className="break-all font-mono text-[10px] text-[var(--muted)]">Celery task: {run.celery_task_id}</span>
          </div>
          <dl className="grid gap-3 rounded-2xl border border-[var(--line)] bg-[var(--panel-solid)] p-4 text-xs sm:grid-cols-3">
            <div><dt className="text-[var(--muted)]">Started</dt><dd className="mt-1 font-semibold">{formatDateTime(run.started_at)}</dd></div>
            <div><dt className="text-[var(--muted)]">Finished</dt><dd className="mt-1 font-semibold">{formatDateTime(run.finished_at)}</dd></div>
            <div><dt className="text-[var(--muted)]">Failed step</dt><dd className="mt-1 break-words font-mono">{run.step_failed ?? "None"}</dd></div>
          </dl>
          <dl className="grid gap-4 rounded-2xl border border-[var(--line)] p-4 text-xs sm:grid-cols-2">
            <div><dt className="text-[var(--muted)]">Company</dt><dd className="mt-1 break-words font-semibold">{run.company_name || "NA"}</dd></div>
            <div><dt className="text-[var(--muted)]">Job title</dt><dd className="mt-1 break-words font-semibold">{run.job_title || "NA"}</dd></div>
            <div><dt className="text-[var(--muted)]">Package (INR)</dt><dd className="mt-1 break-words font-semibold">{run.package || "NA"}</dd></div>
            <div><dt className="text-[var(--muted)]">Platform</dt><dd className="mt-1 break-words font-semibold">{run.platform || "NA"}</dd></div>
            <div className="sm:col-span-2"><dt className="text-[var(--muted)]">Job URL</dt><dd className="mt-1 break-all">{run.job_url}</dd></div>
          </dl>
          {run.error && <div role="alert" className="flex gap-3 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm"><TriangleAlert className="size-5 shrink-0 text-red-500" /><p className="break-words">{run.error}</p></div>}
          {skipQuery.data && <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-4"><p className="text-sm font-bold">Skipped · {skipQuery.data.reason}</p><p className="mt-2 text-sm">{skipQuery.data.details}</p><p className="mt-2 break-all font-mono text-xs text-[var(--muted)]">{skipQuery.data.job_url}</p></div>}
          {skipQuery.isError && <ErrorState title="Skip reason unavailable" message={skipQuery.error.message} compact />}
          <div className="grid gap-5 lg:grid-cols-2">
            <JsonPanel title="Request payload" value={run.payload} />
            <JsonPanel title="Task result" value={run.result} />
          </div>
          <section>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-bold"><FileText className="size-4 text-[var(--blue)]" />Step logs</h3>
              <span className="text-xs text-[var(--muted)]">{logs.length} entries · refreshes every 10s</span>
            </div>
            {logsQuery.isLoading ? <LoadingState label="Loading task logs" /> : logsQuery.isError ? (
              <ErrorState title="Logs unavailable" message={logsQuery.error.message} compact />
            ) : logs.length ? (
              <ol className="space-y-3">
                {logs.map((log) => (
                  <li key={log.id} className="rounded-2xl border border-[var(--line)] bg-[var(--panel-solid)] p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={log.level === "error" ? "danger" : log.level === "warning" ? "warning" : "info"}>{log.level}</StatusBadge>
                      <span className="break-all font-mono text-xs font-semibold">{log.step}</span>
                      <span className="ml-auto flex items-center gap-1 text-[10px] text-[var(--muted)]"><Clock3 className="size-3" />{formatDateTime(log.created_at)}</span>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap break-words text-sm">{log.message}</p>
                    {log.details !== null && <pre className="scrollbar-thin mt-3 max-h-52 overflow-auto rounded-xl bg-[var(--soft)] p-3 text-[11px] leading-5">{JSON.stringify(log.details, null, 2)}</pre>}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="rounded-2xl border border-dashed border-[var(--line)] p-6 text-center text-sm text-[var(--muted)]">{run.status === "running" ? "This task is still running. Buffered logs are saved when it succeeds or fails." : "No step logs were recorded for this task."}</p>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}
