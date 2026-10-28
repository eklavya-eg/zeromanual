import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { Schedule, WorkflowRun } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTime(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDuration(run: WorkflowRun) {
  if (!run.finished_at) return run.status === "running" ? "In progress" : "—";
  const duration = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  if (duration < 1000) return `${duration} ms`;
  if (duration < 60_000) return `${Math.round(duration / 1000)} sec`;
  return `${Math.round(duration / 60_000)} min`;
}

export function scheduleLabel(schedule: Schedule) {
  const cadence =
    schedule.recurrence === "daily"
      ? "Every day"
      : schedule.recurrence === "monthly"
        ? `Monthly · day ${schedule.day_of_month}`
        : `Yearly · ${new Intl.DateTimeFormat(undefined, { month: "short" }).format(
            new Date(2026, (schedule.month ?? 1) - 1, 1),
          )} ${schedule.day_of_month}`;
  const timing =
    schedule.schedule_type === "time"
      ? schedule.time_of_day?.slice(0, 5)
      : `${schedule.range_start?.slice(0, 5)} – ${schedule.range_end?.slice(0, 5)}`;
  return `${cadence} · ${timing}`;
}

export function shortId(id: string) {
  return `${id.slice(0, 6)}…${id.slice(-4)}`;
}

export function runTone(status: string) {
  if (status === "succeeded") return "success" as const;
  if (status === "failed") return "danger" as const;
  if (status === "running") return "info" as const;
  return "neutral" as const;
}
