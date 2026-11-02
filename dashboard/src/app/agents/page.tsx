"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Bot, Braces, CheckCircle2, Clock3, Copy, ExternalLink, Pencil, Play, Plus, Server, Trash2, Waypoints } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Field, inputClass, textareaClass } from "@/components/form-fields";
import { QueryAlert } from "@/components/query-alert";
import { AddButton, Button, Card, EmptyState, Modal, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { SubAgent, SubAgentInput } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const emptyForm: SubAgentInput = { name: "", description: "", invoke_url: "http://127.0.0.1:8001/invoke", enabled: true };

export default function AgentsPage() {
  const queryClient = useQueryClient();
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: api.agents.list });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SubAgent | null>(null);
  const [form, setForm] = useState<SubAgentInput>(emptyForm);
  const [trialAgent, setTrialAgent] = useState<SubAgent | null>(null);
  const [trialPayload, setTrialPayload] = useState("{}");
  const [trialError, setTrialError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const saveAgent = useMutation({
    mutationFn: () => editing ? api.agents.update(editing.id, form) : api.agents.create(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
    },
  });

  const deleteAgent = useMutation({
    mutationFn: api.agents.remove,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });

  const invokeAgent = useMutation({
    mutationFn: async () => {
      if (!trialAgent) throw new Error("Choose a sub-agent first.");
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(trialPayload) as Record<string, unknown>;
      } catch {
        throw new Error("Payload must be valid JSON.");
      }
      return api.agents.invoke(trialAgent.id, payload);
    },
    onMutate: () => setTrialError(null),
    onError: (error) => setTrialError(error.message),
  });

  function beginCreate() {
    setEditing(null);
    setForm(emptyForm);
    setOpen(true);
  }

  function beginEdit(agent: SubAgent) {
    setEditing(agent);
    setForm({ name: agent.name, description: agent.description, invoke_url: agent.invoke_url, enabled: agent.enabled });
    setOpen(true);
  }

  function beginTrial(agent: SubAgent) {
    setTrialAgent(agent);
    setTrialPayload(
      agent.name.toLowerCase().includes("browser")
        ? '{\n  "task": "Open example.com and return the page title",\n  "max_steps": 10\n}'
        : "{\n  \"task\": \"Describe the trial task\"\n}",
    );
    setTrialError(null);
    invokeAgent.reset();
  }

  const agents = agentsQuery.data ?? [];
  return (
    <div>
      <PageHeader eyebrow="Service discovery" title="Sub-agents" description="Register detachable services once, then reuse them across every workflow stack." action={<AddButton onClick={beginCreate}>Register agent</AddButton>} />
      <QueryAlert show={agentsQuery.isError} />
      {deleteAgent.isError && <p className="mb-4 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{deleteAgent.error.message}</p>}

      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Server className="size-5" /></div><div><p className="text-2xl font-semibold tracking-tight">{agents.length}</p><p className="text-xs text-[var(--muted)]">Registered services</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-600"><CheckCircle2 className="size-5" /></div><div><p className="text-2xl font-semibold tracking-tight">{agents.filter((agent) => agent.enabled).length}</p><p className="text-xs text-[var(--muted)]">Enabled agents</p></div></Card>
        <Card className="flex items-center gap-4 p-5"><div className="grid size-11 place-items-center rounded-2xl bg-violet-50 text-violet-600"><Waypoints className="size-5" /></div><div><p className="text-2xl font-semibold tracking-tight">/invoke</p><p className="text-xs text-[var(--muted)]">Shared API contract</p></div></Card>
      </div>

      {agents.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent, index) => (
            <Card key={agent.id} className="group overflow-hidden p-0 transition hover:-translate-y-0.5 hover:shadow-[0_20px_50px_rgba(30,31,45,.09)]">
              <div className={`h-1.5 ${index % 3 === 0 ? "bg-[#7088f5]" : index % 3 === 1 ? "bg-[#b187ec]" : "bg-[#efad83]"}`} />
              <div className="p-5">
                <div className="flex items-start justify-between gap-3"><div className="grid size-12 place-items-center rounded-[18px] bg-gradient-to-br from-[#edf0ff] to-[#fafbff] text-[var(--blue)]"><Bot className="size-5" /></div><div className="flex gap-2"><StatusBadge tone={agent.enabled ? "success" : "neutral"}>{agent.enabled ? "Enabled" : "Disabled"}</StatusBadge><button onClick={() => beginEdit(agent)} className="grid size-8 place-items-center rounded-xl border border-black/[0.07] bg-white text-[var(--muted)] transition hover:text-[var(--ink)]" aria-label={`Edit ${agent.name}`}><Pencil className="size-3.5" /></button><button onClick={() => { if (window.confirm(`Delete "${agent.name}"?`)) deleteAgent.mutate(agent.id); }} className="grid size-8 place-items-center rounded-xl border border-red-100 bg-red-50 text-red-500 transition hover:bg-red-100" aria-label={`Delete ${agent.name}`}><Trash2 className="size-3.5" /></button></div></div>
                <h2 className="mt-5 text-lg font-semibold tracking-[-0.025em]">{agent.name}</h2>
                <p className="mt-2 min-h-10 text-sm leading-5 text-[var(--muted)]">{agent.description || "No description provided."}</p>
                <Button className="mt-4 w-full rounded-xl text-xs" onClick={() => beginTrial(agent)} disabled={!agent.enabled}><Play className="size-3.5" />Try a payload</Button>
                <div className="mt-4 flex items-center gap-2 rounded-2xl bg-black/[0.025] px-3 py-2.5 font-mono text-[11px] text-[#646774]"><span className="size-2 shrink-0 rounded-full bg-emerald-500" /><span className="truncate">{agent.invoke_url}</span><ExternalLink className="ml-auto size-3.5 shrink-0" /></div>
                <div className="mt-4 flex items-center gap-2 text-[11px] text-[var(--muted)]"><Clock3 className="size-3.5" />Updated {formatDateTime(agent.modified_at)}</div>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card><EmptyState icon={<Bot className="size-5" />} title="Register your first sub-agent" description="Add the browser agent or any service exposing POST /invoke." action={<Button onClick={beginCreate}><Plus className="size-4" />Register agent</Button>} /></Card>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? "Edit sub-agent" : "Register sub-agent"} description="The scheduler sends fixed workflow payloads to this endpoint.">
        <form onSubmit={(event) => { event.preventDefault(); saveAgent.mutate(); }} className="space-y-4">
          <Field label="Service name"><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className={inputClass} placeholder="Browser Agent" /></Field>
          <Field label="Description"><textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} className={textareaClass} placeholder="Navigates websites and extracts job details." /></Field>
          <Field label="Invoke URL" hint="POST endpoint"><input required type="url" value={form.invoke_url} onChange={(event) => setForm({ ...form, invoke_url: event.target.value })} className={inputClass} /></Field>
          <label className="flex items-center justify-between rounded-2xl border border-black/[0.07] bg-white px-4 py-3"><div><p className="text-sm font-semibold">Enabled</p><p className="mt-0.5 text-xs text-[var(--muted)]">Available when building workflows</p></div><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} className="size-5 accent-[var(--blue)]" /></label>
          {saveAgent.isError && <p className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{saveAgent.error.message}</p>}
          <div className="flex justify-end gap-2 pt-2"><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" disabled={saveAgent.isPending}>{saveAgent.isPending ? "Saving…" : editing ? "Save changes" : "Register agent"}</Button></div>
        </form>
      </Modal>

      <Modal
        open={trialAgent !== null}
        onClose={() => setTrialAgent(null)}
        title={`Try ${trialAgent?.name ?? "sub-agent"}`}
        description="Send an ad-hoc payload through Switch without creating a workflow."
        wide
      >
        <div className="grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
          <section>
            <div className="mb-3 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Request payload</p><p className="mt-1 text-xs text-[var(--muted)]">JSON sent to the registered /invoke endpoint</p></div><Braces className="size-4 text-violet-600" /></div>
            <textarea value={trialPayload} onChange={(event) => setTrialPayload(event.target.value)} spellCheck={false} className={`${textareaClass} min-h-[340px] bg-[#171923] text-[#dfe4ff] focus:border-blue-400`} />
            <div className="mt-3 rounded-2xl bg-black/[0.025] px-4 py-3 font-mono text-[10px] text-[var(--muted)]">POST {trialAgent?.invoke_url}</div>
          </section>
          <section>
            <div className="mb-3 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Async task</p><p className="mt-1 text-xs text-[var(--muted)]">Switch returns immediately; the result arrives by webhook</p></div>{invokeAgent.data && <StatusBadge tone="info">{invokeAgent.data.status}</StatusBadge>}</div>
            <div className="min-h-[340px] rounded-[22px] border border-black/[0.07] bg-white p-4">
              {invokeAgent.isPending ? <div className="grid min-h-[300px] place-items-center text-center"><div><span className="mx-auto block size-8 animate-spin rounded-full border-2 border-blue-100 border-t-[var(--blue)]" /><p className="mt-4 text-sm font-bold">Queuing task</p><p className="mt-1 text-xs text-[var(--muted)]">This should only take a moment.</p></div></div> : invokeAgent.data ? <div className="grid min-h-[300px] place-items-center text-center"><div className="max-w-md"><div className="mx-auto grid size-12 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Bell className="size-5" /></div><p className="mt-4 text-sm font-bold">Task queued</p><p className="mt-1 text-xs leading-5 text-[var(--muted)]">The browser agent is running in the background. Its payload and response will appear on the Notifications page.</p><div className="mt-4 rounded-xl bg-black/[0.035] px-3 py-2 font-mono text-[10px] text-[var(--muted)]">{invokeAgent.data.task_id}</div><Link href="/notifications" onClick={() => setTrialAgent(null)} className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--blue)] px-4 text-xs font-semibold text-white"><Bell className="size-3.5" />View notifications</Link></div></div> : <div className="grid min-h-[300px] place-items-center text-center"><div><div className="mx-auto grid size-11 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Play className="size-5" /></div><p className="mt-4 text-sm font-bold">Ready for a trial</p><p className="mt-1 max-w-xs text-xs leading-5 text-[var(--muted)]">Review the payload, then queue the agent task.</p></div></div>}
            </div>
            {trialError && <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">{trialError}</p>}
          </section>
        </div>
        <div className="mt-5 flex justify-end gap-2"><Button variant="ghost" onClick={() => setTrialAgent(null)}>Close</Button>{invokeAgent.data && <Button variant="ghost" onClick={async () => { await navigator.clipboard.writeText(invokeAgent.data?.task_id ?? ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }}><Copy className="size-4" />{copied ? "Copied" : "Copy task ID"}</Button>}<Button onClick={() => invokeAgent.mutate()} disabled={invokeAgent.isPending}><Play className="size-4" />{invokeAgent.isPending ? "Queuing…" : "Queue task"}</Button></div>
      </Modal>
    </div>
  );
}
