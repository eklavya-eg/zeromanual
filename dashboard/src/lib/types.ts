export type SubAgent = {
  id: string;
  name: string;
  description: string;
  invoke_url: string;
  enabled: boolean;
  created_at: string;
  modified_at: string;
};

export type WorkflowStep = {
  id: string;
  position: number;
  sub_agent_id: string;
  payload: Record<string, unknown>;
};

export type Workflow = {
  id: string;
  name: string;
  description: string;
  total_sub_agents: number;
  enabled: boolean;
  steps: WorkflowStep[];
  created_at: string;
  modified_at: string;
};

export type ScheduleType = "time" | "range";
export type Recurrence = "daily" | "monthly" | "yearly";

export type Schedule = {
  id: string;
  workflow_id: string;
  schedule_type: ScheduleType;
  recurrence: Recurrence;
  time_of_day: string | null;
  range_start: string | null;
  range_end: string | null;
  day_of_month: number | null;
  month: number | null;
  run_if_missed: boolean;
  misfire_grace_minutes: number;
  enabled: boolean;
  windows_task_name: string | null;
  registration_error: string | null;
  created_at: string;
  modified_at: string;
};

export type RunStatus = "running" | "succeeded" | "failed" | string;

export type WorkflowRun = {
  id: string;
  workflow_id: string;
  schedule_id: string | null;
  occurrence_key: string | null;
  status: RunStatus;
  attempt_count: number;
  scheduled_for: string | null;
  started_at: string;
  finished_at: string | null;
  error: string | null;
};

export type RunStep = {
  id: string;
  workflow_step_id: string;
  attempt_number: number;
  status: RunStatus;
  response: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
};

export type AgentTrialResponse = {
  agent_id: string;
  agent_name: string;
  status: string;
  duration_ms: number;
  result: Record<string, unknown>;
};

export type SubAgentInput = {
  name: string;
  description: string;
  invoke_url: string;
  enabled?: boolean;
};

export type WorkflowInput = {
  name: string;
  description: string;
  enabled?: boolean;
  steps: Array<{
    sub_agent_id: string;
    payload: Record<string, unknown>;
  }>;
};

export type ScheduleInput = {
  workflow_id: string;
  schedule_type: ScheduleType;
  recurrence: Recurrence;
  time_of_day?: string | null;
  range_start?: string | null;
  range_end?: string | null;
  day_of_month?: number | null;
  month?: number | null;
  run_if_missed: boolean;
  misfire_grace_minutes: number;
  enabled?: boolean;
};
