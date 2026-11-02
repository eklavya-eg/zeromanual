"use client";

import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Bot, Braces, Check, CirclePlay, Eye, GitBranch, GripVertical, Layers3, Pencil, Plus, Search, Trash2, Workflow as WorkflowIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Field, inputClass, textareaClass } from "@/components/form-fields";
import { QueryAlert } from "@/components/query-alert";
import { AddButton, Button, Card, EmptyState, Modal, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { SubAgent, Workflow } from "@/lib/types";
import { cn } from "@/lib/utils";

type DraftStep = { key: string; sub_agent_id: string; payloadText: string };

export default function WorkflowsPage() {
  const queryClient = useQueryClient();
  const [workflowsQuery, agentsQuery, schedulesQuery] = useQueries({ queries: [
    { queryKey: ["workflows"], queryFn: api.workflows.list },
    { queryKey: ["agents"], queryFn: api.agents.list },
    { queryKey: ["schedules"], queryFn: () => api.schedules.list() },
  ] });
  const [builderOpen, setBuilderOpen] = useState(false);
  const [editingWorkflow, setEditingWorkflow] = useState<Workflow | null>(null);
  const [viewingWorkflow, setViewingWorkflow] = useState<Workflow | null>(null);
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [steps, setSteps] = useState<DraftStep[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [builderError, setBuilderError] = useState<string | null>(null);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const params = new URLSearchParams(window.location.search);
      if (params.get("new") === "true") setBuilderOpen(true);
      if (params.get("q")) setSearch(params.get("q") ?? "");
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  const workflows = useMemo(() => workflowsQuery.data ?? [], [workflowsQuery.data]);
  const agents = agentsQuery.data ?? [];
  const schedules = schedulesQuery.data ?? [];
  const filtered = useMemo(() => workflows.filter((workflow) => `${workflow.name} ${workflow.description}`.toLowerCase().includes(search.toLowerCase())), [workflows, search]);
  const selectedStep = steps.find((step) => step.key === selectedKey) ?? null;

  const saveWorkflow = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new Error("Give the workflow a name.");
      if (!steps.length) throw new Error("Add at least one sub-agent step.");
      const parsedSteps = steps.map((step, index) => {
        try { return { sub_agent_id: step.sub_agent_id, payload: JSON.parse(step.payloadText) as Record<string, unknown> }; }
        catch { throw new Error(`Step ${index + 1} has invalid JSON.`); }
      });
      const input = { name: name.trim(), description: description.trim(), enabled, steps: parsedSteps };
      return editingWorkflow
        ? api.workflows.update(editingWorkflow.id, input)
        : api.workflows.create(input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      resetBuilder();
    },
    onError: (error) => setBuilderError(error.message),
  });

  const deleteWorkflow = useMutation({
    mutationFn: api.workflows.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      setViewingWorkflow(null);
    },
  });

  const runWorkflow = useMutation({
    mutationFn: api.workflows.run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
  });

  function resetBuilder() {
    setBuilderOpen(false); setEditingWorkflow(null); setName(""); setDescription(""); setEnabled(true); setSteps([]); setSelectedKey(null); setBuilderError(null);
  }

  function beginCreate() {
    resetBuilder();
    setBuilderOpen(true);
  }

  function beginEdit(workflow: Workflow) {
    const draftSteps = workflow.steps.map((step) => ({
      key: step.id,
      sub_agent_id: step.sub_agent_id,
      payloadText: JSON.stringify(step.payload, null, 2),
    }));
    setEditingWorkflow(workflow);
    setName(workflow.name);
    setDescription(workflow.description);
    setEnabled(workflow.enabled);
    setSteps(draftSteps);
    setSelectedKey(draftSteps[0]?.key ?? null);
    setBuilderError(null);
    setBuilderOpen(true);
  }

  function confirmDelete(workflow: Workflow) {
    if (window.confirm(`Delete "${workflow.name}" and its schedules and run history?`)) {
      deleteWorkflow.mutate(workflow.id);
    }
  }

  function addAgent(agent: SubAgent) {
    const step = { key: crypto.randomUUID(), sub_agent_id: agent.id, payloadText: "{\n  \"task\": \"Describe the task for this agent\"\n}" };
    setSteps((current) => [...current, step]);
    setSelectedKey(step.key);
  }

  function updateSelected(payloadText: string) {
    if (!selectedKey) return;
    setSteps((current) => current.map((step) => step.key === selectedKey ? { ...step, payloadText } : step));
  }

  function moveStep(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= steps.length) return;
    const next = [...steps];
    [next[index], next[target]] = [next[target], next[index]];
    setSteps(next);
  }

  const unavailable = [workflowsQuery, agentsQuery, schedulesQuery].some((query) => query.isError);
  return (
    <div>
      <PageHeader eyebrow="Automation studio" title="Workflows" description="Arrange sub-agents into a clear execution stack and decide exactly what each service receives." action={<AddButton onClick={beginCreate}>Create workflow</AddButton>} />
      <QueryAlert show={unavailable} />

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-md flex-1"><Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search workflows" className={`${inputClass} pl-11`} /></div>
        <div className="flex items-center gap-2 text-xs text-[var(--muted)]"><span className="rounded-full bg-white px-3 py-2 ring-1 ring-black/[0.06]">{workflows.length} total</span><span className="rounded-full bg-emerald-50 px-3 py-2 text-emerald-700">{workflows.filter((item) => item.enabled).length} enabled</span></div>
      </div>

      {filtered.length ? (
        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {filtered.map((workflow, index) => {
            const workflowSchedules = schedules.filter((schedule) => schedule.workflow_id === workflow.id);
            return (
              <Card key={workflow.id} className="group p-5 transition hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(30,31,45,.09)]">
                <div className="flex items-start justify-between"><div className={cn("grid size-12 place-items-center rounded-[18px]", index % 3 === 0 ? "bg-blue-50 text-[var(--blue)]" : index % 3 === 1 ? "bg-violet-50 text-violet-600" : "bg-orange-50 text-orange-600")}><GitBranch className="size-5" /></div><div className="flex items-center gap-2"><StatusBadge tone={workflow.enabled ? "success" : "neutral"}>{workflow.enabled ? "Enabled" : "Disabled"}</StatusBadge><button onClick={() => setViewingWorkflow(workflow)} className="grid size-8 place-items-center rounded-xl border border-black/[0.07] bg-white text-[var(--muted)] hover:text-[var(--ink)]" aria-label={`View ${workflow.name}`}><Eye className="size-3.5" /></button><button onClick={() => beginEdit(workflow)} className="grid size-8 place-items-center rounded-xl border border-black/[0.07] bg-white text-[var(--muted)] hover:text-[var(--ink)]" aria-label={`Edit ${workflow.name}`}><Pencil className="size-3.5" /></button><button onClick={() => confirmDelete(workflow)} className="grid size-8 place-items-center rounded-xl border border-red-100 bg-red-50 text-red-500 hover:bg-red-100" aria-label={`Delete ${workflow.name}`}><Trash2 className="size-3.5" /></button></div></div>
                <h2 className="mt-5 text-lg font-semibold tracking-[-0.03em]">{workflow.name}</h2><p className="mt-2 min-h-10 text-sm leading-5 text-[var(--muted)]">{workflow.description || "No workflow description."}</p>
                <div className="mt-5 flex items-center gap-2 overflow-hidden">
                  {workflow.steps.slice(0, 4).map((step, stepIndex) => <div key={step.id} className="flex items-center"><div className="grid size-8 place-items-center rounded-xl border border-blue-100 bg-blue-50 text-[10px] font-bold text-[var(--blue)]">{stepIndex + 1}</div>{stepIndex < Math.min(workflow.steps.length, 4) - 1 && <div className="h-px w-3 bg-blue-200" />}</div>)}
                  <span className="ml-1 text-xs text-[var(--muted)]">{workflow.total_sub_agents} step{workflow.total_sub_agents === 1 ? "" : "s"}</span>
                </div>
                <div className="mt-5 flex items-center justify-between border-t border-black/[0.06] pt-4"><div className="flex items-center gap-2 text-xs text-[var(--muted)]"><Layers3 className="size-3.5" />{workflowSchedules.length} schedule{workflowSchedules.length === 1 ? "" : "s"}</div><Button className="h-9 rounded-xl px-3 text-xs" variant="ghost" onClick={() => runWorkflow.mutate(workflow.id)} disabled={runWorkflow.isPending}><CirclePlay className="size-3.5" />Run now</Button></div>
              </Card>
            );
          })}
        </div>
      ) : <Card><EmptyState icon={<WorkflowIcon className="size-5" />} title={workflows.length ? "No matching workflows" : "Create your first workflow"} description="Choose agents, arrange the stack, and give every step a fixed JSON payload." action={!workflows.length ? <Button onClick={beginCreate}><Plus className="size-4" />Create workflow</Button> : undefined} /></Card>}

      <Modal open={viewingWorkflow !== null} onClose={() => setViewingWorkflow(null)} title={viewingWorkflow?.name ?? "Workflow"} description={viewingWorkflow?.description || "No workflow description."} wide>
        {viewingWorkflow && <div><div className="mb-4 flex items-center gap-2"><StatusBadge tone={viewingWorkflow.enabled ? "success" : "neutral"}>{viewingWorkflow.enabled ? "Enabled" : "Disabled"}</StatusBadge><span className="text-xs text-[var(--muted)]">{viewingWorkflow.total_sub_agents} step{viewingWorkflow.total_sub_agents === 1 ? "" : "s"}</span></div><div className="space-y-3">{viewingWorkflow.steps.map((step) => { const agent = agents.find((item) => item.id === step.sub_agent_id); return <section key={step.id} className="rounded-2xl border border-black/[0.07] bg-white p-4"><div className="mb-3 flex items-center gap-3"><span className="grid size-8 place-items-center rounded-xl bg-[var(--ink)] text-xs font-bold text-white">{step.position}</span><div><p className="text-sm font-bold">{agent?.name ?? "Unknown agent"}</p><p className="text-[10px] text-[var(--muted)]">{step.sub_agent_id}</p></div></div><pre className="max-h-64 overflow-auto rounded-2xl bg-[#171923] p-4 text-[11px] leading-5 text-[#dfe4ff]">{JSON.stringify(step.payload, null, 2)}</pre></section>; })}</div><div className="mt-5 flex justify-end gap-2"><Button variant="danger" onClick={() => confirmDelete(viewingWorkflow)} disabled={deleteWorkflow.isPending}><Trash2 className="size-4" />Delete</Button><Button onClick={() => { setViewingWorkflow(null); beginEdit(viewingWorkflow); }}><Pencil className="size-4" />Edit workflow</Button></div>{deleteWorkflow.isError && <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{deleteWorkflow.error.message}</p>}</div>}
      </Modal>

      <Modal open={builderOpen} onClose={resetBuilder} title={editingWorkflow ? "Edit workflow" : "Create workflow"} description={editingWorkflow ? "Update the workflow metadata, execution order, and payloads." : "Compose a deterministic stack of detachable agent services."} wide>
        <div className="mb-5 grid gap-4 sm:grid-cols-[1fr_1fr_auto]"><Field label="Workflow name"><input value={name} onChange={(event) => setName(event.target.value)} className={inputClass} placeholder="Daily job discovery" /></Field><Field label="Description"><input value={description} onChange={(event) => setDescription(event.target.value)} className={inputClass} placeholder="Find, score, and notify me about roles." /></Field><label className="flex min-w-36 items-center justify-between gap-4 rounded-2xl border border-black/[0.07] bg-white px-4 py-3 sm:mt-6"><span className="text-sm font-semibold">Enabled</span><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="size-5 accent-[var(--blue)]" /></label></div>
        <div className="grid min-h-[470px] gap-4 lg:grid-cols-[.8fr_1.1fr_1fr]">
          <section className="rounded-[22px] border border-black/[0.07] bg-white p-4"><div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Agent catalog</p><p className="mt-1 text-xs text-[var(--muted)]">Click to add</p></div><Bot className="size-4 text-[var(--blue)]" /></div><div className="space-y-2">{agents.filter((agent) => agent.enabled).map((agent) => <button key={agent.id} onClick={() => addAgent(agent)} className="flex w-full items-center gap-3 rounded-2xl border border-black/[0.06] p-3 text-left transition hover:border-blue-200 hover:bg-blue-50/50"><div className="grid size-9 shrink-0 place-items-center rounded-xl bg-black/[0.035]"><Bot className="size-4" /></div><div className="min-w-0"><p className="truncate text-xs font-bold">{agent.name}</p><p className="mt-0.5 truncate text-[10px] text-[var(--muted)]">{agent.description || agent.invoke_url}</p></div><Plus className="ml-auto size-3.5 text-[var(--blue)]" /></button>)}{!agents.length && <p className="rounded-2xl bg-amber-50 p-3 text-xs text-amber-700">Register a sub-agent before creating a workflow.</p>}</div></section>
          <section className="soft-grid rounded-[22px] border border-black/[0.07] bg-[#fafaf8] p-4"><div className="mb-4 flex items-center justify-between"><p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Execution stack</p><span className="text-[10px] text-[var(--muted)]">{steps.length} steps</span></div><div className="space-y-2">{steps.map((step, index) => { const agent = agents.find((item) => item.id === step.sub_agent_id); return <div key={step.key} onClick={() => setSelectedKey(step.key)} className={cn("flex cursor-pointer items-center gap-2 rounded-2xl border bg-white p-3 transition", selectedKey === step.key ? "border-blue-300 ring-4 ring-blue-100/70" : "border-black/[0.06]")}><GripVertical className="size-4 text-[#b1b3bb]" /><span className="grid size-7 place-items-center rounded-lg bg-[var(--ink)] text-[10px] font-bold text-white">{index + 1}</span><div className="min-w-0 flex-1"><p className="truncate text-xs font-bold">{agent?.name ?? "Unknown agent"}</p><p className="mt-0.5 text-[10px] text-[var(--muted)]">Fixed payload configured</p></div><div className="flex"><button onClick={(event) => { event.stopPropagation(); moveStep(index, -1); }} aria-label="Move step up" className="grid size-7 place-items-center rounded-lg hover:bg-black/[0.04]"><ArrowUp className="size-3" /></button><button onClick={(event) => { event.stopPropagation(); moveStep(index, 1); }} aria-label="Move step down" className="grid size-7 place-items-center rounded-lg hover:bg-black/[0.04]"><ArrowDown className="size-3" /></button><button onClick={(event) => { event.stopPropagation(); setSteps((current) => current.filter((item) => item.key !== step.key)); }} aria-label="Remove step" className="grid size-7 place-items-center rounded-lg text-red-500 hover:bg-red-50"><Trash2 className="size-3" /></button></div></div>; })}{!steps.length && <div className="grid min-h-64 place-items-center text-center"><div><div className="mx-auto grid size-11 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Layers3 className="size-5" /></div><p className="mt-3 text-xs font-bold">Your stack is empty</p><p className="mt-1 text-[10px] text-[var(--muted)]">Add agents from the catalog.</p></div></div>}</div></section>
          <section className="rounded-[22px] border border-black/[0.07] bg-white p-4"><div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Payload inspector</p><p className="mt-1 text-xs text-[var(--muted)]">JSON sent to /invoke</p></div><Braces className="size-4 text-violet-600" /></div>{selectedStep ? <><textarea value={selectedStep.payloadText} onChange={(event) => updateSelected(event.target.value)} spellCheck={false} className={`${textareaClass} min-h-[330px] bg-[#161822] text-[#dfe4ff] focus:border-blue-400`} /><div className="mt-3 flex items-center gap-2 text-[10px] text-emerald-700"><Check className="size-3" />Saved with this step</div></> : <div className="grid min-h-72 place-items-center text-center text-xs text-[var(--muted)]">Select a step to edit its payload.</div>}</section>
        </div>
        {(builderError || saveWorkflow.isError) && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{builderError ?? saveWorkflow.error?.message}</p>}
        <div className="mt-5 flex justify-end gap-2"><Button variant="ghost" onClick={resetBuilder}>Cancel</Button><Button onClick={() => { setBuilderError(null); saveWorkflow.mutate(); }} disabled={saveWorkflow.isPending}>{saveWorkflow.isPending ? "Saving…" : editingWorkflow ? "Save changes" : "Create workflow"}</Button></div>
      </Modal>
    </div>
  );
}
