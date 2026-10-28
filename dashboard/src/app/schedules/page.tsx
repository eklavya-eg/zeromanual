"use client";

import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { AlarmClock, CalendarClock, CheckCircle2, Clock3, Pencil, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";

import { Field, inputClass, Segmented } from "@/components/form-fields";
import { QueryAlert } from "@/components/query-alert";
import { AddButton, Button, Card, EmptyState, Modal, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { Recurrence, Schedule, ScheduleInput, ScheduleType } from "@/lib/types";
import { scheduleLabel } from "@/lib/utils";

type FormState = {
  workflow_id: string;
  schedule_type: ScheduleType;
  recurrence: Recurrence;
  time_of_day: string;
  range_start: string;
  range_end: string;
  day_of_month: number;
  month: number;
  run_if_missed: boolean;
  misfire_grace_minutes: number;
  enabled: boolean;
};

const defaultForm: FormState = { workflow_id: "", schedule_type: "time", recurrence: "daily", time_of_day: "21:00", range_start: "21:00", range_end: "23:00", day_of_month: 1, month: 1, run_if_missed: true, misfire_grace_minutes: 120, enabled: true };

export default function SchedulesPage() {
  const queryClient = useQueryClient();
  const [schedulesQuery, workflowsQuery] = useQueries({ queries: [
    { queryKey: ["schedules"], queryFn: () => api.schedules.list() },
    { queryKey: ["workflows"], queryFn: api.workflows.list },
  ] });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [form, setForm] = useState<FormState>(defaultForm);

  const schedules = schedulesQuery.data ?? [];
  const workflows = workflowsQuery.data ?? [];

  function toInput(): ScheduleInput {
    return {
      workflow_id: form.workflow_id,
      schedule_type: form.schedule_type,
      recurrence: form.recurrence,
      time_of_day: form.schedule_type === "time" ? form.time_of_day : null,
      range_start: form.schedule_type === "range" ? form.range_start : null,
      range_end: form.schedule_type === "range" ? form.range_end : null,
      day_of_month: form.recurrence === "daily" ? null : form.day_of_month,
      month: form.recurrence === "yearly" ? form.month : null,
      run_if_missed: form.run_if_missed,
      misfire_grace_minutes: form.misfire_grace_minutes,
      enabled: form.enabled,
    };
  }

  const saveSchedule = useMutation({
    mutationFn: () => editing ? api.schedules.update(editing.id, toInput()) : api.schedules.create(toInput()),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["schedules"] }); setOpen(false); setEditing(null); },
  });
  const deleteSchedule = useMutation({ mutationFn: api.schedules.remove, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schedules"] }) });
  const reconcile = useMutation({ mutationFn: api.schedules.reconcile, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }) });

  function beginCreate() { setEditing(null); setForm({ ...defaultForm, workflow_id: workflows[0]?.id ?? "" }); setOpen(true); }
  function beginEdit(schedule: Schedule) {
    setEditing(schedule);
    setForm({ workflow_id: schedule.workflow_id, schedule_type: schedule.schedule_type, recurrence: schedule.recurrence, time_of_day: schedule.time_of_day?.slice(0, 5) ?? "21:00", range_start: schedule.range_start?.slice(0, 5) ?? "21:00", range_end: schedule.range_end?.slice(0, 5) ?? "23:00", day_of_month: schedule.day_of_month ?? 1, month: schedule.month ?? 1, run_if_missed: schedule.run_if_missed, misfire_grace_minutes: schedule.misfire_grace_minutes, enabled: schedule.enabled });
    setOpen(true);
  }

  const preview = `${form.recurrence === "daily" ? "Every day" : form.recurrence === "monthly" ? `Every month on day ${form.day_of_month}` : `Every year in month ${form.month} on day ${form.day_of_month}`}, ${form.schedule_type === "time" ? `at ${form.time_of_day}` : `between ${form.range_start} and ${form.range_end}`}.`;
  return (
    <div>
      <PageHeader eyebrow="Time orchestration" title="Schedules" description="Give each workflow as many exact times or active ranges as it needs." action={<div className="flex gap-2"><Button variant="ghost" onClick={() => reconcile.mutate()} disabled={reconcile.isPending}><RefreshCw className={`size-4 ${reconcile.isPending ? "animate-spin" : ""}`} />Reconcile</Button><AddButton onClick={beginCreate} disabled={!workflows.length}>Add schedule</AddButton></div>} />
      <QueryAlert show={schedulesQuery.isError || workflowsQuery.isError} />

      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><CalendarClock className="size-5" /></div><div><p className="text-2xl font-semibold">{schedules.length}</p><p className="text-xs text-[var(--muted)]">Schedule entries</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-violet-50 text-violet-600"><Clock3 className="size-5" /></div><div><p className="text-2xl font-semibold">{schedules.filter((item) => item.schedule_type === "time").length}</p><p className="text-xs text-[var(--muted)]">Exact-time triggers</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-600"><ShieldCheck className="size-5" /></div><div><p className="text-2xl font-semibold">{schedules.filter((item) => item.run_if_missed).length}</p><p className="text-xs text-[var(--muted)]">Recovery enabled</p></div></Card>
      </div>

      {schedules.length ? <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">{schedules.map((schedule) => { const workflow = workflows.find((item) => item.id === schedule.workflow_id); return <Card key={schedule.id} className="p-5 transition hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(30,31,45,.09)]"><div className="flex items-start justify-between"><div className={`grid size-12 place-items-center rounded-[18px] ${schedule.schedule_type === "time" ? "bg-blue-50 text-[var(--blue)]" : "bg-violet-50 text-violet-600"}`}>{schedule.schedule_type === "time" ? <AlarmClock className="size-5" /> : <CalendarClock className="size-5" />}</div><div className="flex gap-2"><StatusBadge tone={schedule.enabled ? "success" : "neutral"}>{schedule.enabled ? "Enabled" : "Disabled"}</StatusBadge><button onClick={() => beginEdit(schedule)} className="grid size-8 place-items-center rounded-xl border border-black/[0.07] bg-white" aria-label="Edit schedule"><Pencil className="size-3.5" /></button></div></div><p className="mt-5 text-xs font-semibold uppercase tracking-wider text-[var(--blue)]">{schedule.schedule_type} · {schedule.recurrence}</p><h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">{workflow?.name ?? "Unknown workflow"}</h2><p className="mt-2 text-sm text-[var(--muted)]">{scheduleLabel(schedule)}</p><div className="mt-5 space-y-2 rounded-2xl bg-black/[0.025] p-3 text-xs"><div className="flex justify-between"><span className="text-[var(--muted)]">Missed run</span><span className="font-semibold">{schedule.run_if_missed ? `Recover within ${schedule.misfire_grace_minutes} min` : "Skip"}</span></div><div className="flex justify-between"><span className="text-[var(--muted)]">Windows task</span><span className={schedule.registration_error ? "text-red-600" : "font-semibold text-emerald-700"}>{schedule.registration_error ? "Needs attention" : schedule.windows_task_name ? "Registered" : "Local monitor"}</span></div></div><div className="mt-4 flex justify-end"><Button variant="danger" className="h-8 rounded-xl px-3 text-xs" onClick={() => confirm("Delete this schedule?") && deleteSchedule.mutate(schedule.id)}><Trash2 className="size-3" />Delete</Button></div></Card>; })}</div> : <Card><EmptyState icon={<CalendarClock className="size-5" />} title="No schedules configured" description={workflows.length ? "Add an exact time or active range to one of your workflows." : "Create a workflow before adding schedules."} action={workflows.length ? <Button onClick={beginCreate}><Plus className="size-4" />Add schedule</Button> : undefined} /></Card>}

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? "Edit schedule" : "Add schedule"} description="Times use the Windows server local timezone.">
        <form onSubmit={(event) => { event.preventDefault(); saveSchedule.mutate(); }} className="space-y-4">
          <Field label="Workflow"><select required value={form.workflow_id} onChange={(event) => setForm({ ...form, workflow_id: event.target.value })} className={inputClass}><option value="">Select workflow</option>{workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name}</option>)}</select></Field>
          <Field label="Schedule type"><Segmented value={form.schedule_type} onChange={(value) => setForm({ ...form, schedule_type: value })} options={[{ value: "time", label: "Exact time" }, { value: "range", label: "Time range" }]} /></Field>
          {form.schedule_type === "time" ? <Field label="Time"><input type="time" required value={form.time_of_day} onChange={(event) => setForm({ ...form, time_of_day: event.target.value })} className={inputClass} /></Field> : <div className="grid grid-cols-2 gap-3"><Field label="Start"><input type="time" required value={form.range_start} onChange={(event) => setForm({ ...form, range_start: event.target.value })} className={inputClass} /></Field><Field label="End"><input type="time" required value={form.range_end} onChange={(event) => setForm({ ...form, range_end: event.target.value })} className={inputClass} /></Field></div>}
          <Field label="Recurrence"><select value={form.recurrence} onChange={(event) => setForm({ ...form, recurrence: event.target.value as Recurrence })} className={inputClass}><option value="daily">Every day</option><option value="monthly">Every month</option><option value="yearly">Every year</option></select></Field>
          {form.recurrence !== "daily" && <div className="grid grid-cols-2 gap-3">{form.recurrence === "yearly" && <Field label="Month"><input type="number" min="1" max="12" value={form.month} onChange={(event) => setForm({ ...form, month: Number(event.target.value) })} className={inputClass} /></Field>}<Field label="Day of month"><input type="number" min="1" max="31" value={form.day_of_month} onChange={(event) => setForm({ ...form, day_of_month: Number(event.target.value) })} className={inputClass} /></Field></div>}
          <label className="flex items-center justify-between rounded-2xl border border-black/[0.07] bg-white px-4 py-3"><div><p className="text-sm font-semibold">Run when server returns</p><p className="mt-0.5 text-xs text-[var(--muted)]">Recover an exact-time occurrence after downtime</p></div><input type="checkbox" checked={form.run_if_missed} onChange={(event) => setForm({ ...form, run_if_missed: event.target.checked })} className="size-5 accent-[var(--blue)]" /></label>
          {form.run_if_missed && <Field label="Recovery window" hint="minutes"><input type="number" min="0" value={form.misfire_grace_minutes} onChange={(event) => setForm({ ...form, misfire_grace_minutes: Number(event.target.value) })} className={inputClass} /></Field>}
          <div className="rounded-2xl bg-gradient-to-r from-blue-50 to-violet-50 p-4"><div className="flex gap-3"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--blue)]" /><div><p className="text-xs font-bold">Schedule preview</p><p className="mt-1 text-xs leading-5 text-[var(--muted)]">{preview}</p></div></div></div>
          {saveSchedule.isError && <p className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{saveSchedule.error.message}</p>}
          <div className="flex justify-end gap-2 pt-2"><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" disabled={saveSchedule.isPending}>{saveSchedule.isPending ? "Saving…" : editing ? "Save changes" : "Add schedule"}</Button></div>
        </form>
      </Modal>
    </div>
  );
}
