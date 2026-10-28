"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, Braces, CheckCircle2, Clock3, Copy, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";

import { ErrorState, LoadingState, PageHeader, StatusBadge, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, formatDuration, runTone, shortId } from "@/lib/utils";

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [copied, setCopied] = useState(false);
  const [runsQuery, workflowsQuery] = useQueries({ queries: [
    { queryKey: ["runs"], queryFn: () => api.runs.list(), refetchInterval: 10_000 },
    { queryKey: ["workflows"], queryFn: api.workflows.list },
  ] });
  const stepsQuery = useQuery({ queryKey: ["run-steps", id], queryFn: () => api.runs.steps(id), refetchInterval: 10_000 });
  const run = runsQuery.data?.find((item) => item.id === id);
  const workflow = workflowsQuery.data?.find((item) => item.id === run?.workflow_id);

  if (runsQuery.isLoading || stepsQuery.isLoading) return <LoadingState label="Loading run timeline" />;
  if (runsQuery.isError || stepsQuery.isError || !run) return <ErrorState title="Run unavailable" message="The run could not be loaded. It may have been removed or the API is offline." />;
  const steps = stepsQuery.data ?? [];

  return (
    <div>
      <Link href="/runs" className="mb-5 inline-flex items-center gap-2 text-xs font-bold text-[var(--muted)] hover:text-[var(--ink)]"><ArrowLeft className="size-4" />Back to runs</Link>
      <PageHeader eyebrow="Run detail" title={workflow?.name ?? "Workflow run"} description={`Run ${shortId(run.id)} · ${run.schedule_id ? "Scheduled occurrence" : "Manual trigger"}`} action={<StatusBadge tone={runTone(run.status)}>{run.status}</StatusBadge>} />
      <div className="grid gap-4 sm:grid-cols-4"><Card className="p-5"><p className="text-xs text-[var(--muted)]">Started</p><p className="mt-2 text-sm font-bold">{formatDateTime(run.started_at)}</p></Card><Card className="p-5"><p className="text-xs text-[var(--muted)]">Duration</p><p className="mt-2 text-sm font-bold">{formatDuration(run)}</p></Card><Card className="p-5"><p className="text-xs text-[var(--muted)]">Attempt</p><p className="mt-2 text-sm font-bold">#{run.attempt_count}</p></Card><Card className="p-5"><p className="text-xs text-[var(--muted)]">Occurrence</p><p className="mt-2 truncate text-sm font-bold">{run.occurrence_key ?? "Manual"}</p></Card></div>
      {run.error && <div className="mt-5 flex gap-3 rounded-[22px] border border-red-100 bg-red-50 p-5 text-sm text-red-800"><TriangleAlert className="size-5 shrink-0" /><div><p className="font-bold">Workflow failed</p><p className="mt-1 text-xs leading-5 text-red-700">{run.error}</p></div></div>}
      <div className="mt-6 grid gap-5 xl:grid-cols-[1fr_.48fr]">
        <Card className="p-6"><div className="mb-6 flex items-center justify-between"><div><h2 className="text-sm font-bold">Execution timeline</h2><p className="mt-1 text-xs text-[var(--muted)]">Ordered sub-agent attempts</p></div><span className="text-xs text-[var(--muted)]">{steps.length} steps</span></div>{steps.length ? <div>{steps.map((step, index) => <div key={step.id} className="relative flex gap-4 pb-7 last:pb-0">{index < steps.length - 1 && <div className="absolute left-[19px] top-10 h-[calc(100%-2rem)] w-px bg-black/[0.09]" />}<div className={`relative z-10 grid size-10 shrink-0 place-items-center rounded-2xl ${step.status === "succeeded" ? "bg-emerald-50 text-emerald-600" : step.status === "failed" ? "bg-red-50 text-red-600" : "bg-blue-50 text-[var(--blue)]"}`}>{step.status === "succeeded" ? <CheckCircle2 className="size-4" /> : <Bot className="size-4" />}</div><div className="min-w-0 flex-1 rounded-[20px] border border-black/[0.06] bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-xs font-bold">Step {index + 1}</p><p className="mt-1 font-mono text-[10px] text-[var(--muted)]">{shortId(step.workflow_step_id)}</p></div><StatusBadge tone={runTone(step.status)}>{step.status}</StatusBadge></div>{step.error && <p className="mt-3 rounded-xl bg-red-50 p-3 text-xs text-red-700">{step.error}</p>}<div className="mt-3 flex items-center gap-2 text-[10px] text-[var(--muted)]"><Clock3 className="size-3" />{formatDateTime(step.started_at)} · attempt {step.attempt_number}</div></div></div>)}</div> : <p className="py-12 text-center text-xs text-[var(--muted)]">No step records are available.</p>}</Card>
        <Card className="h-fit p-6"><div className="flex items-center justify-between"><div><h2 className="text-sm font-bold">Raw run record</h2><p className="mt-1 text-xs text-[var(--muted)]">Useful for debugging and support</p></div><Braces className="size-4 text-violet-600" /></div><pre className="scrollbar-thin mt-5 max-h-[480px] overflow-auto rounded-[20px] bg-[#171923] p-4 text-[10px] leading-5 text-[#dce1ff]">{JSON.stringify({ run, steps }, null, 2)}</pre><button onClick={async () => { await navigator.clipboard.writeText(JSON.stringify({ run, steps }, null, 2)); setCopied(true); setTimeout(() => setCopied(false), 1500); }} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-black/[0.07] bg-white py-2.5 text-xs font-bold"><Copy className="size-3.5" />{copied ? "Copied" : "Copy JSON"}</button></Card>
      </div>
    </div>
  );
}
