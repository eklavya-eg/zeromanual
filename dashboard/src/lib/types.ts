export type SubAgent = {
  id: string;
  name: string;
  description: string;
  invoke_url: string;
  enabled: boolean;
  created_at: string;
  modified_at: string;
};

export type WorkflowStepType = "sub_agent" | "command";

export type WorkflowStepInput =
  | { step_type?: "sub_agent"; sub_agent_id: string; payload: Record<string, unknown> }
  | { step_type: "command"; sub_agent_id: null; command: string; working_directory: string | null; timeout_seconds: number; payload?: Record<string, unknown> };

export type WorkflowStep = {
  id: string;
  position: number;
  step_type: WorkflowStepType;
  sub_agent_id: string | null;
  payload: Record<string, unknown>;
  command: string | null;
  working_directory: string | null;
  timeout_seconds: number;
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
  task_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
};

export type SubAgentNotification = {
  kind?: "sub_agent";
  job_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  payload: Record<string, unknown>;
  response: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  completed_at: string;
};

export type WorkflowRunNotification = {
  kind: "workflow_run";
  run_id: string;
  workflow_id: string;
  workflow_name: string;
  attempt_count: number;
  status: "succeeded" | "failed";
  error: string | null;
  created_at: string;
  completed_at: string;
};

export type AppNotification = SubAgentNotification | WorkflowRunNotification;

export type NotificationSocketMessage =
  | { type: "ping" }
  | { type: "notification"; data: AppNotification };

export type Worker = {
  id: string;
  name: string;
  enabled: boolean;
  created_at: string;
  modified_at: string;
};

export type WorkerTaskRun = {
  id: string;
  worker_id: string;
  celery_task_id: string;
  job_url: string;
  company_name: string;
  job_title: string;
  package: string;
  platform: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  status: string;
  started: boolean;
  success: boolean;
  failed: boolean;
  step_failed: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
};

export type WorkerDashboard = {
  worker: Worker;
  metrics: {
    total_runs: number;
    running: number;
    succeeded: number;
    failed: number;
    skipped: number;
    success_rate: number | null;
  };
  runs: WorkerTaskRun[];
  total: number;
  page: number;
  page_size: number;
};

export type WorkerSkip = {
  id: string;
  task_run_id: string;
  job_url: string;
  reason: string;
  details: string;
  created_at: string;
};

export type WorkerLog = {
  id: string;
  worker_id: string;
  task_run_id: string;
  level: string;
  step: string;
  message: string;
  details: Record<string, unknown> | null;
  created_at: string;
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
  steps: WorkflowStepInput[];
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
