"use client";

import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowUpRight, Bot, CalendarClock, CheckCircle2, CirclePlay, GitBranch, Radar, RotateCcw, Sparkles, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { QueryAlert } from "@/components/query-alert";
import { Button, Card, EmptyState, MetricCard, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, runTone, scheduleLabel } from "@/lib/utils";

export default function OverviewPage() {
  const queryClient = useQueryClient();
  const [today, setToday] = useState<Date | null>(null);
  const [agentsQuery, workflowsQuery, schedulesQuery, runsQuery] = useQueries({
    queries: [
      { queryKey: ["agents"], queryFn: api.agents.list },
      { queryKey: ["workflows"], queryFn: api.workflows.list },
      { queryKey: ["schedules"], queryFn: () => api.schedules.list() },
      { queryKey: ["runs"], queryFn: () => api.runs.list(), refetchInterval: 20_000 },
    ],
  });
  const agents = agentsQuery.data ?? [];
  const workflows = workflowsQuery.data ?? [];
  const schedules = schedulesQuery.data ?? [];
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const hasError = [agentsQuery, workflowsQuery, schedulesQuery, runsQuery].some((query) => query.isError);
  const successful = runs.filter((run) => run.status === "succeeded").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  const successRate = runs.length ? Math.round((successful / runs.length) * 100) : 0;

  useEffect(() => {
    const frame = requestAnimationFrame(() => setToday(new Date()));
    return () => cancelAnimationFrame(frame);
  }, []);

  const chartData = useMemo(() => !today ? [] : Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setDate(date.getDate() - (6 - index));
    const dayRuns = runs.filter((run) => new Date(run.started_at).toDateString() === date.toDateString());
    return { day: new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(date), success: dayRuns.filter((run) => run.status === "succeeded").length, failed: dayRuns.filter((run) => run.status === "failed").length };
  }), [runs, today]);

  const reconcile = useMutation({ mutationFn: api.schedules.reconcile, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }) });

  return (
    <div>
      <PageHeader eyebrow="Agent operations" title="Good evening, Eklavya" description="Everything scheduled, running, and waiting across your job-switch agent stack." action={<Button variant="ghost" onClick={() => reconcile.mutate()} disabled={reconcile.isPending}><RotateCcw className={`size-4 ${reconcile.isPending ? "animate-spin" : ""}`} />Reconcile now</Button>} />
      <QueryAlert show={hasError} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Active workflows" value={workflows.filter((item) => item.enabled).length} detail={`${workflows.length} workflows configured`} icon={<GitBranch className="size-5" />} />
        <MetricCard label="Enabled schedules" value={schedules.filter((item) => item.enabled).length} detail="Across exact times and ranges" icon={<CalendarClock className="size-5" />} accent="violet" />
        <MetricCard label="Available agents" value={agents.filter((item) => item.enabled).length} detail={`${agents.length} services registered`} icon={<Bot className="size-5" />} accent="peach" />
        <MetricCard label="Success rate" value={`${successRate}%`} detail={`${failed} failed run${failed === 1 ? "" : "s"} recorded`} icon={<CheckCircle2 className="size-5" />} accent="mint" />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.45fr_.9fr]">
        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between px-6 pt-6"><div><p className="text-sm font-bold">Execution pulse</p><p className="mt-1 text-xs text-[var(--muted)]">Completed and failed runs over seven days</p></div><StatusBadge tone={runs.some((run) => run.status === "running") ? "info" : "neutral"}>{runs.some((run) => run.status === "running") ? "Live" : "Quiet"}</StatusBadge></div>
          <div className="h-[300px] px-2 pb-3 pt-8">
            <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ left: -24, right: 16 }}><defs><linearGradient id="success" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5472f3" stopOpacity={0.38} /><stop offset="100%" stopColor="#5472f3" stopOpacity={0.02} /></linearGradient><linearGradient id="failed" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f38c74" stopOpacity={0.25} /><stop offset="100%" stopColor="#f38c74" stopOpacity={0.01} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9e9e7" strokeDasharray="4 6" /><XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: "#8c8e98", fontSize: 11 }} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#8c8e98", fontSize: 11 }} /><Tooltip contentStyle={{ borderRadius: 16, border: "1px solid rgba(0,0,0,.06)", boxShadow: "0 12px 30px rgba(0,0,0,.08)", fontSize: 12 }} /><Area type="monotone" dataKey="success" stroke="#5472f3" strokeWidth={2.5} fill="url(#success)" /><Area type="monotone" dataKey="failed" stroke="#ef826b" strokeWidth={2} fill="url(#failed)" /></AreaChart></ResponsiveContainer>
          </div>
        </Card>

        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-black/[0.06] px-6 py-5"><div><p className="text-sm font-bold">Next schedules</p><p className="mt-1 text-xs text-[var(--muted)]">Upcoming workflow triggers</p></div><Link href="/schedules" className="text-xs font-bold text-[var(--blue)]">View all</Link></div>
          {schedules.length ? <div className="divide-y divide-black/[0.05] px-3">{schedules.slice(0, 5).map((schedule, index) => { const workflow = workflows.find((item) => item.id === schedule.workflow_id); return <div key={schedule.id} className="flex items-center gap-4 rounded-2xl px-3 py-4 transition hover:bg-black/[0.025]"><div className={`grid size-10 shrink-0 place-items-center rounded-2xl ${index % 2 ? "bg-violet-50 text-violet-600" : "bg-blue-50 text-[var(--blue)]"}`}><CalendarClock className="size-4" /></div><div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{workflow?.name ?? "Unknown workflow"}</p><p className="mt-1 truncate text-xs text-[var(--muted)]">{scheduleLabel(schedule)}</p></div><ArrowUpRight className="size-4 text-[#b0b2ba]" /></div>; })}</div> : <EmptyState icon={<CalendarClock className="size-5" />} title="No schedules yet" description="Attach an exact time or active range to a workflow." />}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_.8fr]">
        <Card className="p-0">
          <div className="flex items-center justify-between border-b border-black/[0.06] px-6 py-5"><div><p className="text-sm font-bold">Recent activity</p><p className="mt-1 text-xs text-[var(--muted)]">Latest workflow execution state</p></div><Link href="/runs" className="text-xs font-bold text-[var(--blue)]">Open runs</Link></div>
          {runs.length ? <div className="divide-y divide-black/[0.05]">{runs.slice(0, 5).map((run) => { const workflow = workflows.find((item) => item.id === run.workflow_id); return <Link href={`/runs/${run.id}`} key={run.id} className="flex items-center gap-4 px-6 py-4 transition hover:bg-black/[0.02]"><div className="grid size-9 place-items-center rounded-xl bg-black/[0.035]"><Activity className="size-4" /></div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{workflow?.name ?? "Workflow run"}</p><p className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(run.started_at)}</p></div><StatusBadge tone={runTone(run.status)}>{run.status}</StatusBadge></Link>; })}</div> : <EmptyState icon={<Radar className="size-5" />} title="No run activity" description="Run a workflow manually or wait for a schedule to trigger." />}
        </Card>

        <Card className="relative overflow-hidden p-6"><div className="absolute -right-16 -top-16 size-48 rounded-full bg-gradient-to-br from-blue-300/40 to-violet-300/10 blur-2xl" /><div className="relative"><div className="grid size-11 place-items-center rounded-2xl bg-[var(--ink)] text-white"><Sparkles className="size-5" /></div><h2 className="mt-5 text-xl font-semibold tracking-[-0.03em]">Build your next automation</h2><p className="mt-2 max-w-sm text-sm leading-6 text-[var(--muted)]">Stack your browser, discovery, matching, and notification agents into one repeatable workflow.</p><div className="mt-6 flex flex-wrap gap-2"><Link href="/workflows?new=true" className="inline-flex h-11 items-center gap-2 rounded-2xl bg-[var(--blue)] px-4 text-sm font-semibold text-white shadow-lg shadow-blue-500/20"><CirclePlay className="size-4" />New workflow</Link><Link href="/agents" className="inline-flex h-11 items-center gap-2 rounded-2xl border border-black/[0.08] bg-white px-4 text-sm font-semibold"><Bot className="size-4" />Add agent</Link></div><div className="mt-7 flex items-center gap-2 text-xs text-[var(--muted)]">{failed > 0 ? <TriangleAlert className="size-4 text-amber-500" /> : <CheckCircle2 className="size-4 text-emerald-500" />}{failed > 0 ? `${failed} runs need attention` : "No unresolved run failures"}</div></div></Card>
      </div>
    </div>
  );
}
