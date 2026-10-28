import type {
  AgentTrialResponse,
  RunStep,
  Schedule,
  ScheduleInput,
  SubAgent,
  SubAgentInput,
  Workflow,
  WorkflowInput,
  WorkflowRun,
} from "@/lib/types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_SWITCH_API_URL ?? "/api"
).replace(/\/$/, "");

const scheduledUrl = `${API_BASE_URL}/scheduled`;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${scheduledUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  agents: {
    list: () => request<SubAgent[]>("/sub-agents"),
    create: (input: SubAgentInput) =>
      request<SubAgent>("/sub-agents", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (id: string, input: Partial<SubAgentInput>) =>
      request<SubAgent>(`/sub-agents/${id}`, {
        method: "PATCH",
        body: JSON.stringify(input),
      }),
    invoke: (id: string, payload: Record<string, unknown>) =>
      request<AgentTrialResponse>(`/sub-agents/${id}/invoke`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  workflows: {
    list: () => request<Workflow[]>("/workflows"),
    create: (input: WorkflowInput) =>
      request<Workflow>("/workflows", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    run: (id: string) =>
      request<WorkflowRun>(`/run/${id}`, { method: "POST" }),
  },
  schedules: {
    list: (workflowId?: string) =>
      request<Schedule[]>(
        `/schedules${workflowId ? `?workflow_id=${workflowId}` : ""}`,
      ),
    create: (input: ScheduleInput) =>
      request<Schedule>("/schedules", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (id: string, input: Partial<ScheduleInput>) =>
      request<Schedule>(`/schedules/${id}`, {
        method: "PATCH",
        body: JSON.stringify(input),
      }),
    remove: (id: string) =>
      request<void>(`/schedules/${id}`, { method: "DELETE" }),
    reconcile: () =>
      request<{ triggered_run_ids: string[] }>("/reconcile", {
        method: "POST",
      }),
  },
  runs: {
    list: (workflowId?: string) =>
      request<WorkflowRun[]>(
        `/runs${workflowId ? `?workflow_id=${workflowId}` : ""}`,
      ),
    steps: (id: string) => request<RunStep[]>(`/runs/${id}/steps`),
  },
};
