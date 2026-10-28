"use client";

import { useQueries } from "@tanstack/react-query";
import { Activity, Banknote, Bot, Gauge, TimerReset, TrendingUp } from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { QueryAlert } from "@/components/query-alert";
import { Card, MetricCard, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";

export default function UsagePage() {
  const [runsQuery, workflowsQuery] = useQueries({ queries: [
    { queryKey: ["runs"], queryFn: () => api.runs.list() },
    { queryKey: ["workflows"], queryFn: api.workflows.list },
  ] });
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const workflows = useMemo(() => workflowsQuery.data ?? [], [workflowsQuery.data]);
  const durations = runs.filter((run) => run.finished_at).map((run) => new Date(run.finished_at!).getTime() - new Date(run.started_at).getTime()).sort((a, b) => a - b);
  const median = durations.length ? durations[Math.floor(durations.length / 2)] : 0;
  const chartData = useMemo(() => workflows.slice(0, 8).map((workflow) => ({ name: workflow.name.length > 14 ? `${workflow.name.slice(0, 14)}…` : workflow.name, runs: runs.filter((run) => run.workflow_id === workflow.id).length, failed: runs.filter((run) => run.workflow_id === workflow.id && run.status === "failed").length })), [runs, workflows]);

  return (
    <div>
      <PageHeader eyebrow="Observability" title="Usage" description="Understand throughput, reliability, and execution time across your automation portfolio." />
      <QueryAlert show={runsQuery.isError || workflowsQuery.isError} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Invocations" value={runs.length} detail="Workflow runs recorded" icon={<Activity className="size-5" />} /><MetricCard label="Median duration" value={median ? `${Math.round(median / 1000)}s` : "—"} detail="Across completed runs" icon={<Gauge className="size-5" />} accent="violet" /><MetricCard label="Retries" value={runs.reduce((sum, run) => sum + Math.max(0, run.attempt_count - 1), 0)} detail="Additional occurrence attempts" icon={<TimerReset className="size-5" />} accent="peach" /><MetricCard label="Estimated cost" value="—" detail="Waiting for agent usage metadata" icon={<Banknote className="size-5" />} accent="mint" /></div>
      <div className="mt-5 grid gap-5 xl:grid-cols-[1.3fr_.7fr]">
        <Card className="p-6"><div className="mb-6 flex items-start justify-between"><div><h2 className="text-sm font-bold">Runs by workflow</h2><p className="mt-1 text-xs text-[var(--muted)]">Volume and failure distribution</p></div><TrendingUp className="size-4 text-[var(--blue)]" /></div><div className="h-[330px]"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ left: -20 }}><CartesianGrid vertical={false} stroke="#e9e9e7" strokeDasharray="4 6" /><XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#80828e" }} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#80828e" }} /><Tooltip contentStyle={{ borderRadius: 16, border: "1px solid rgba(0,0,0,.06)", fontSize: 12 }} /><Bar dataKey="runs" fill="#7088f5" radius={[8, 8, 0, 0]} /><Bar dataKey="failed" fill="#ef9b85" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer></div></Card>
        <Card className="p-6"><div className="grid size-11 place-items-center rounded-2xl bg-violet-50 text-violet-600"><Bot className="size-5" /></div><h2 className="mt-5 text-lg font-semibold tracking-[-0.03em]">Agent cost telemetry</h2><p className="mt-2 text-sm leading-6 text-[var(--muted)]">Token, browser-time, and model cost panels will activate when sub-agent responses include standardized usage metadata.</p><div className="mt-6 space-y-3">{["Input and output tokens", "Browser session duration", "Provider and model cost", "Cost per workflow"].map((item) => <div key={item} className="flex items-center gap-3 rounded-2xl bg-black/[0.025] px-4 py-3 text-xs text-[var(--muted)]"><span className="size-2 rounded-full bg-[#c8cad1]" />{item}</div>)}</div></Card>
      </div>
    </div>
  );
}
