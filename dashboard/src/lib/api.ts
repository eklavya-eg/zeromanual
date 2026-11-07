import type {
  AgentTrialResponse,
  RunStep,
  Schedule,
  ScheduleInput,
  SubAgent,
  SubAgentInput,
  AppNotification,
  Workflow,
  WorkflowInput,
  WorkflowRun,
  Worker,
  WorkerDashboard,
  WorkerLog,
  WorkerSkip,
  WorkerTaskRun,
} from "@/lib/types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_EYE_API_URL ??
  process.env.NEXT_PUBLIC_SWITCH_API_URL ??
  "/api"
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

async function request<T>(
  path: string,
  init?: RequestInit,
  baseUrl = scheduledUrl,
): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
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
    remove: (id: string) =>
      request<void>(`/sub-agents/${id}`, { method: "DELETE" }),
    invoke: (id: string, payload: Record<string, unknown>) =>
      request<AgentTrialResponse>(`/sub-agents/${id}/invoke`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  workflows: {
    list: () => request<Workflow[]>("/workflows"),
    get: (id: string) => request<Workflow>(`/workflows/${id}`),
    create: (input: WorkflowInput, commandToken?: string) =>
      request<Workflow>("/workflows", {
        method: "POST",
        headers: commandToken ? { "X-Eye-Command-Token": commandToken } : {},
        body: JSON.stringify(input),
      }),
    update: (id: string, input: Partial<WorkflowInput>, commandToken?: string) =>
      request<Workflow>(`/workflows/${id}`, {
        method: "PATCH",
        headers: commandToken ? { "X-Eye-Command-Token": commandToken } : {},
        body: JSON.stringify(input),
      }),
    remove: (id: string) =>
      request<void>(`/workflows/${id}`, { method: "DELETE" }),
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
  workers: {
    list: () => request<Worker[]>("/workers", undefined, API_BASE_URL),
    dashboard: (id: string, page = 1, status?: string) => {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (status) params.set("status", status);
      return request<WorkerDashboard>(
        `/workers/${encodeURIComponent(id)}/dashboard?${params}`,
        undefined,
        API_BASE_URL,
      );
    },
    run: (id: string) =>
      request<WorkerTaskRun>(`/workers/runs/${encodeURIComponent(id)}`, undefined, API_BASE_URL),
    logs: (id: string) =>
      request<WorkerLog[]>(`/workers/runs/${encodeURIComponent(id)}/logs`, undefined, API_BASE_URL),
    skip: (id: string) =>
      request<WorkerSkip | null>(`/workers/runs/${encodeURIComponent(id)}/skip`, undefined, API_BASE_URL),
  },
  notifications: {
    list: () =>
      request<AppNotification[]>("", undefined, `${API_BASE_URL}/notifications`),
  },
};

export function notificationSocketUrl(): string {
  const configured =
    process.env.NEXT_PUBLIC_EYE_WS_URL ?? process.env.NEXT_PUBLIC_SWITCH_WS_URL;
  if (configured) return configured;

  const apiUrl = new URL(API_BASE_URL, window.location.origin);
  apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  apiUrl.pathname = `${apiUrl.pathname.replace(/\/$/, "")}/notifications/ws`;
  return apiUrl.toString();
}
